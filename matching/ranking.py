import os
import re
from collections import Counter

from matching.hard_filters import get_hard_filter_reason
from matching.profile_library import (
    DEFAULT_NEGATIVE_PROFILE_TEXTS,
    build_profile_specs,
)
from shared.descriptions import build_matching_text


EMBEDDING_MODEL_NAME = os.getenv(
    "JOB_SCRAPER_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
DEFAULT_MIN_PROFILE_SCORE = float(os.getenv("JOB_SCRAPER_MIN_SCORE", "0.43"))
SENIORITY_PENALTY_FLOOR = 0.35
DEFAULT_SENIORITY_PENALTY_WEIGHT = float(
    os.getenv("JOB_SCRAPER_SENIORITY_PENALTY_WEIGHT", "0.18")
)
DEFAULT_SALARY_PENALTY_MAX = 0.35

SALARY_RANGE_PATTERNS = [
    re.compile(
        r"(?:£|gbp\s*)\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?"
        r"\s*(?:-|to|–|—)\s*(?:£|gbp\s*)?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:salary|compensation|pay)\D{0,20}(?:£|gbp\s*)\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?",
        flags=re.IGNORECASE,
    ),
]
SALARY_RATE_MARKERS = ("hour", "day", "daily", "week", "monthly")

_PROFILE_MATCHER = None


class ProfileMatcher:
    def __init__(self, model_name):
        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError as exc:
            raise RuntimeError(
                "Semantic job matching requires sentence-transformers. "
                "Install dependencies from requirements.txt."
            ) from exc

        self.model = SentenceTransformer(model_name)
        self.util = util
        self.description_embedding_cache = {}
        self.profile_embedding_cache = {}
        self.negative_embedding_cache = {}

    def _get_description_embedding(self, description):
        if description not in self.description_embedding_cache:
            self.description_embedding_cache[description] = self.model.encode(
                description,
                normalize_embeddings=True,
            )
        return self.description_embedding_cache[description]

    def _get_profile_embeddings(self, profile_specs):
        cache_key = tuple((spec["id"], spec["text"]) for spec in profile_specs)
        if cache_key not in self.profile_embedding_cache:
            self.profile_embedding_cache[cache_key] = self.model.encode(
                [spec["text"] for spec in profile_specs],
                normalize_embeddings=True,
            )
        return self.profile_embedding_cache[cache_key]

    def _get_negative_embeddings(self, negative_profile_texts):
        normalized_negative_texts = tuple(
            text.strip()
            for text in (negative_profile_texts or DEFAULT_NEGATIVE_PROFILE_TEXTS)
            if text and text.strip()
        )
        if not normalized_negative_texts:
            return None

        if normalized_negative_texts not in self.negative_embedding_cache:
            self.negative_embedding_cache[normalized_negative_texts] = self.model.encode(
                list(normalized_negative_texts),
                normalize_embeddings=True,
            )

        return self.negative_embedding_cache[normalized_negative_texts]

    def score_description(self, description, profile_specs, negative_profile_texts=None):
        description_embedding = self._get_description_embedding(description)
        profile_embeddings = self._get_profile_embeddings(profile_specs)
        similarities = self.util.cos_sim(
            description_embedding,
            profile_embeddings,
        )[0].tolist()

        profile_scores = {
            spec["label"]: score
            for spec, score in zip(profile_specs, similarities)
        }
        ranked_profiles = sorted(
            profile_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        top_profile, top_score = ranked_profiles[0]
        if len(ranked_profiles) > 1:
            second_profile, second_score = ranked_profiles[1]
        else:
            second_profile, second_score = top_profile, 0.0

        negative_embeddings = self._get_negative_embeddings(negative_profile_texts)
        seniority_penalty_score = 0.0
        if negative_embeddings is not None:
            seniority_penalty_score = max(
                self.util.cos_sim(
                    description_embedding,
                    negative_embeddings,
                )[0].tolist()
            )

        return {
            "profile_scores": profile_scores,
            "top_profile": top_profile,
            "top_score": top_score,
            "second_profile": second_profile,
            "second_score": second_score,
            "score_margin": top_score - second_score,
            "seniority_penalty_score": seniority_penalty_score,
            "fit_summary": format_fit_summary(ranked_profiles),
        }


def get_profile_matcher():
    global _PROFILE_MATCHER

    if _PROFILE_MATCHER is None:
        _PROFILE_MATCHER = ProfileMatcher(EMBEDDING_MODEL_NAME)

    return _PROFILE_MATCHER


def score_to_percent(score):
    return max(0, round(score * 100))


def format_fit_summary(ranked_profiles):
    return " | ".join(
        f"{label} {score_to_percent(score)}%"
        for label, score in ranked_profiles
    )


def apply_seniority_penalty(score_data, recipient_profile):
    seniority_penalty_weight = float(
        recipient_profile.get(
            "seniority_penalty_weight",
            DEFAULT_SENIORITY_PENALTY_WEIGHT,
        )
    )
    seniority_penalty_applied = max(
        0.0,
        score_data["seniority_penalty_score"] - SENIORITY_PENALTY_FLOOR,
    ) * seniority_penalty_weight
    ranking_score = score_data["top_score"] - seniority_penalty_applied
    return ranking_score, seniority_penalty_applied


def _parse_salary_amount(amount_text, has_k_suffix):
    numeric_value = float(amount_text.replace(",", ""))
    if has_k_suffix:
        numeric_value *= 1000
    return numeric_value


def extract_salary_upper_bound_gbp(text):
    normalized_text = text or ""
    upper_bounds = []

    for pattern in SALARY_RANGE_PATTERNS:
        for match in pattern.finditer(normalized_text):
            trailing_context = normalized_text[match.end() : match.end() + 20].lower()
            if any(marker in trailing_context for marker in SALARY_RATE_MARKERS):
                continue

            groups = match.groups()
            if len(groups) >= 4 and groups[2]:
                upper_bounds.append(_parse_salary_amount(groups[2], groups[3]))
                continue

            upper_bounds.append(_parse_salary_amount(groups[0], groups[1]))

    if not upper_bounds:
        return None

    return max(upper_bounds)


def apply_salary_penalty(job, ranking_score, recipient_profile):
    preferred_salary_max = recipient_profile.get("preferred_salary_max_gbp")
    if preferred_salary_max is None:
        return ranking_score, None, 0.0

    salary_upper_bound = extract_salary_upper_bound_gbp(
        f"{job.get('title', '')}\n{job.get('description', '')}"
    )
    if salary_upper_bound is None:
        return ranking_score, None, 0.0

    salary_hard_cap = recipient_profile.get("salary_hard_cap_gbp")
    if salary_hard_cap is None:
        salary_hard_cap = preferred_salary_max + 5000

    penalty_max = float(
        recipient_profile.get("salary_penalty_max", DEFAULT_SALARY_PENALTY_MAX)
    )

    if salary_upper_bound <= preferred_salary_max:
        return ranking_score, salary_upper_bound, 0.0

    if salary_hard_cap <= preferred_salary_max:
        salary_hard_cap = preferred_salary_max + 1

    if salary_upper_bound >= salary_hard_cap:
        penalty = penalty_max
    else:
        penalty = penalty_max * (
            (salary_upper_bound - preferred_salary_max)
            / (salary_hard_cap - preferred_salary_max)
        )

    return ranking_score - penalty, salary_upper_bound, penalty


def rank_jobs(jobs, recipient_profile, matcher=None, return_stats=False):
    matcher = matcher or get_profile_matcher()
    profile_specs = build_profile_specs(recipient_profile)
    min_top_score = float(
        recipient_profile.get("min_top_score", DEFAULT_MIN_PROFILE_SCORE)
    )
    ranked_jobs = []
    stats = {
        "input_jobs": len(jobs),
        "hard_filtered_jobs": 0,
        "below_threshold_jobs": 0,
        "ranked_jobs": 0,
        "hard_filter_reasons": {},
    }
    hard_filter_reasons = Counter()

    for job in jobs:
        hard_filter_reason = get_hard_filter_reason(job)
        if hard_filter_reason is not None:
            stats["hard_filtered_jobs"] += 1
            hard_filter_reasons[hard_filter_reason] += 1
            continue

        match_text = build_matching_text(
            job.get("title", ""),
            job.get("description", ""),
        )
        score_data = matcher.score_description(
            match_text,
            profile_specs,
            recipient_profile.get("negative_profile_texts"),
        )
        ranking_score, seniority_penalty_applied = apply_seniority_penalty(
            score_data,
            recipient_profile,
        )
        score_data["seniority_penalty_applied"] = seniority_penalty_applied

        ranking_score, salary_upper_bound, salary_penalty_applied = apply_salary_penalty(
            job,
            ranking_score,
            recipient_profile,
        )
        if ranking_score < min_top_score:
            stats["below_threshold_jobs"] += 1
            continue

        ranked_jobs.append(
            {
                **job,
                **score_data,
                "ranking_score": ranking_score,
                "salary_upper_bound_gbp": salary_upper_bound,
                "salary_penalty_applied": salary_penalty_applied,
            }
        )
        stats["ranked_jobs"] += 1

    ranked_jobs.sort(
        key=lambda job: (
            job["ranking_score"],
            job["top_score"],
            job["score_margin"],
            job["second_score"],
            job["title"].lower(),
        ),
        reverse=True,
    )
    stats["hard_filter_reasons"] = dict(hard_filter_reasons)
    if return_stats:
        return ranked_jobs, stats
    return ranked_jobs
