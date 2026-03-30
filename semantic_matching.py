import os
import re
from collections import Counter

from filters import (
    AUTHORIZATION_MISMATCH_PATTERNS,
    ELIGIBILITY_REJECT_PATTERNS,
    HARD_COMMERCIAL_TERMS,
    HARD_ELIGIBILITY_TITLE_TERMS,
    HARD_SENIORITY_TERMS,
)
from recipient_profiles import DEFAULT_SEMANTIC_PROFILES
from utils import is_uk_location, passes_experience_filter


EMBEDDING_MODEL_NAME = os.getenv(
    "JOB_SCRAPER_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
DEFAULT_MIN_PROFILE_SCORE = float(os.getenv("JOB_SCRAPER_MIN_SCORE", "0.43"))
SENIORITY_PENALTY_FLOOR = 0.35
DEFAULT_SENIORITY_PENALTY_WEIGHT = float(
    os.getenv("JOB_SCRAPER_SENIORITY_PENALTY_WEIGHT", "0.18")
)
SPONSOR_EXPLICIT_YES_BOOST = 0.03
SPONSOR_LOOKUP_BOOST = 0.02
SPONSOR_IMPLIED_NO_PENALTY = 0.08
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

SEMANTIC_PROFILE_LIBRARY = {
    "swe": {
        "label": "SWE",
        "text": (
            "Early-career software engineer profile. Builds practical software "
            "systems with a strong Python foundation and experience working across "
            "application logic, data processing, APIs, structured file parsing, "
            "and user-facing tools. Has built end-to-end project components "
            "including a document parser that converts unstructured PDFs into valid "
            "JSON, a semantic query system that translates English text into "
            "structured queries, a mobile rehabilitation application, and a "
            "cloud-backed analytics dashboard. Comfortable writing clean "
            "application code, handling data flow between components, integrating "
            "external services, and building tools that are reliable and "
            "understandable. Also has exposure to full-stack and product-style "
            "work through Flutter/Dart, Firebase, Streamlit, and backend data "
            "handling. Best aligned with junior software engineering roles, "
            "backend-leaning roles, and generalist engineering roles where strong "
            "problem solving, Python, and structured systems thinking matter more "
            "than a specific web framework."
        ),
    },
    "data_science": {
        "label": "Data Science",
        "text": (
            "Early-career data science profile with strong grounding in applied "
            "machine learning, data processing, feature engineering, model "
            "evaluation, and exploratory analysis. Experience includes music "
            "emotion recognition, music genre classification, explainable machine "
            "learning, and research-focused experimentation on real datasets. Has "
            "worked on dimensionality reduction, feature selection, baseline "
            "comparison, performance improvement, and interpretable modelling. "
            "Comfortable using Python, pandas, NumPy, scikit-learn, TensorFlow, "
            "and PyTorch for practical analysis and modelling work. Also has "
            "experience turning messy or unstructured inputs into analysable data "
            "through scraping, parsing, and batch processing. Best aligned with "
            "junior data science, applied analytics, research assistant, and "
            "modelling-focused roles where experimentation, structured reasoning, "
            "and data understanding are central."
        ),
    },
    "ai_ml_engineer": {
        "label": "AI/ML",
        "text": (
            "Early-career AI and machine learning engineer profile focused on "
            "building practical ML-enabled systems end to end. Experience spans "
            "data collection and processing, model training, evaluation, "
            "experimentation, and supporting tooling around machine learning "
            "workflows. Has built ML projects in audio and music domains, "
            "including genre classification and emotion prediction, and has worked "
            "on explainability, representation learning, and domain adaptation. "
            "Also built supporting systems such as a parser that combines rules "
            "and LLM inference to extract structured JSON from PDFs, and a "
            "semantic search/query tool that maps natural language into structured "
            "retrieval. Comfortable with Python ML tooling including TensorFlow, "
            "scikit-learn, PyTorch, pandas, and NumPy. Best aligned with junior ML "
            "engineer, applied AI, AI software, and ML systems roles that combine "
            "software implementation with data and model work."
        ),
    },
}

PROFILE_ID_ALIASES = {
    "aiml": "ai_ml_engineer",
    "ai_ml": "ai_ml_engineer",
    "ai_ml_engineer": "ai_ml_engineer",
    "ai_ml_engineering": "ai_ml_engineer",
    "data science": "data_science",
    "data_science": "data_science",
    "ds": "data_science",
    "software_engineering": "swe",
    "software_engineer": "swe",
    "swe": "swe",
}

DEFAULT_NEGATIVE_PROFILE_TEXTS = [
    (
        "Role aimed at established engineers with proven commercial experience "
        "building, deploying, operating, and owning production systems. Expects "
        "service reliability ownership, on-call exposure, system design depth, "
        "cross-team technical leadership, and multiple years of professional "
        "software or machine learning engineering work."
    ),
    (
        "Senior or staff-level engineering role requiring technical leadership, "
        "mentoring, architecture ownership, production responsibility, and proven "
        "delivery of complex systems at scale across multiple teams."
    ),
]

_PROFILE_MATCHER = None


def normalize_profile_id(value):
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return PROFILE_ID_ALIASES.get(normalized, normalized)


def get_default_semantic_profile_ids():
    return list(DEFAULT_SEMANTIC_PROFILES)


def _display_label(profile_id):
    if profile_id in SEMANTIC_PROFILE_LIBRARY:
        return SEMANTIC_PROFILE_LIBRARY[profile_id]["label"]

    return profile_id.replace("_", " ").title()


def _fallback_profile_text(profile_id):
    label = _display_label(profile_id)
    label_lower = label.lower()
    return (
        f"Early-career {label_lower} profile. Best aligned with junior and "
        f"entry-level {label_lower} roles. Focus on responsibilities, tooling, "
        f"and day-to-day work that match {label_lower} positions."
    )


def build_profile_specs(recipient_profile):
    configured_ids = recipient_profile.get("semantic_profiles") or get_default_semantic_profile_ids()
    custom_texts = {
        normalize_profile_id(profile_id): text
        for profile_id, text in (recipient_profile.get("semantic_profile_texts") or {}).items()
    }
    specs = []

    for raw_profile_id in configured_ids:
        profile_id = normalize_profile_id(raw_profile_id)

        if profile_id in custom_texts:
            specs.append(
                {
                    "id": profile_id,
                    "label": _display_label(profile_id),
                    "text": custom_texts[profile_id],
                }
            )
            continue

        if profile_id not in SEMANTIC_PROFILE_LIBRARY:
            specs.append(
                {
                    "id": profile_id,
                    "label": _display_label(profile_id),
                    "text": _fallback_profile_text(profile_id),
                }
            )
            continue

        profile_entry = SEMANTIC_PROFILE_LIBRARY[profile_id]
        specs.append(
            {
                "id": profile_id,
                "label": profile_entry["label"],
                "text": profile_entry["text"],
            }
        )

    return specs


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


def title_has_hard_reject_term(title, reject_terms):
    normalized_title = (title or "").lower()
    return any(term in normalized_title for term in reject_terms)


def has_authorization_mismatch(description):
    normalized_description = (description or "").lower()
    return any(
        re.search(pattern, normalized_description, flags=re.IGNORECASE)
        for pattern in AUTHORIZATION_MISMATCH_PATTERNS
    )


def has_eligibility_mismatch(description):
    normalized_description = (description or "").lower()
    return any(
        re.search(pattern, normalized_description, flags=re.IGNORECASE)
        for pattern in ELIGIBILITY_REJECT_PATTERNS
    )


def passes_hard_filters(job, max_years_experience=1):
    return get_hard_filter_reason(job, max_years_experience) is None


def get_hard_filter_reason(job, max_years_experience=1):
    title = job.get("title", "")
    description = job.get("description", "")
    locations = job.get("locations") or [job.get("location", "")]

    if title_has_hard_reject_term(title, HARD_SENIORITY_TERMS):
        return "title_seniority"

    if title_has_hard_reject_term(title, HARD_COMMERCIAL_TERMS):
        return "title_commercial"

    if title_has_hard_reject_term(title, HARD_ELIGIBILITY_TITLE_TERMS):
        return "title_eligibility"

    if not is_uk_location(locations):
        return "location"

    if has_authorization_mismatch(description):
        return "authorization"

    if has_eligibility_mismatch(description):
        return "eligibility"

    if not passes_experience_filter(
        description,
        max_years_experience,
    ):
        return "experience"

    return None


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


def apply_sponsorship_adjustments(job, score_data, recipient_profile):
    sponsorship_enabled = (
        recipient_profile.get("care_about_sponsorship", False)
        or recipient_profile.get("use_sponsor_lookup", False)
    )
    if not sponsorship_enabled:
        return score_data["ranking_score"]

    status = job.get("sponsorship_status", "unknown")
    ranking_score = score_data["ranking_score"]

    if recipient_profile.get("care_about_sponsorship", False):
        if status == "explicit_no":
            return None
        if status == "implied_no":
            ranking_score -= SPONSOR_IMPLIED_NO_PENALTY
        elif status == "explicit_yes":
            ranking_score += SPONSOR_EXPLICIT_YES_BOOST

    if (
        recipient_profile.get("use_sponsor_lookup", False)
        and job.get("is_sponsor_licensed_employer")
        and status != "explicit_no"
    ):
        ranking_score += SPONSOR_LOOKUP_BOOST

    return ranking_score


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
        "sponsorship_rejected_jobs": 0,
        "below_threshold_jobs": 0,
        "ranked_jobs": 0,
        "hard_filter_reasons": {},
    }
    hard_filter_reasons = Counter()

    for job in jobs:
        hard_filter_reason = get_hard_filter_reason(
            job,
            recipient_profile.get("max_years_experience", 1),
        )
        if hard_filter_reason is not None:
            stats["hard_filtered_jobs"] += 1
            hard_filter_reasons[hard_filter_reason] += 1
            continue

        score_data = matcher.score_description(
            job.get("description", ""),
            profile_specs,
            recipient_profile.get("negative_profile_texts"),
        )
        ranking_score, seniority_penalty_applied = apply_seniority_penalty(
            score_data,
            recipient_profile,
        )
        score_data["seniority_penalty_applied"] = seniority_penalty_applied
        score_data["ranking_score"] = ranking_score
        ranking_score = apply_sponsorship_adjustments(job, score_data, recipient_profile)
        if ranking_score is None:
            stats["sponsorship_rejected_jobs"] += 1
            continue

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
