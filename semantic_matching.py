import os
import re

from filters import (
    AUTHORIZATION_MISMATCH_PATTERNS,
    HARD_COMMERCIAL_TERMS,
    HARD_SENIORITY_TERMS,
)
from utils import is_uk_location, passes_experience_filter


EMBEDDING_MODEL_NAME = os.getenv(
    "JOB_SCRAPER_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
MIN_PROFILE_SCORE = 0.50

PROFILE_TEXTS = {
    "SWE": (
        "Early-career software engineer profile. Builds practical software systems "
        "with a strong Python foundation and experience working across application "
        "logic, data processing, APIs, structured file parsing, and user-facing "
        "tools. Has built end-to-end project components including a document parser "
        "that converts unstructured PDFs into valid JSON, a semantic query system "
        "that translates English text into structured queries, a mobile "
        "rehabilitation application, and a cloud-backed analytics dashboard. "
        "Comfortable writing clean application code, handling data flow between "
        "components, integrating external services, and building tools that are "
        "reliable and understandable. Also has exposure to full-stack and "
        "product-style work through Flutter/Dart, Firebase, Streamlit, and backend "
        "data handling. Best aligned with junior software engineering roles, "
        "backend-leaning roles, and generalist engineering roles where strong "
        "problem solving, Python, and structured systems thinking matter more than "
        "a specific web framework."
    ),
    "Data Science": (
        "Early-career data science profile with strong grounding in applied machine "
        "learning, data processing, feature engineering, model evaluation, and "
        "exploratory analysis. Experience includes music emotion recognition, music "
        "genre classification, explainable machine learning, and research-focused "
        "experimentation on real datasets. Has worked on dimensionality reduction, "
        "feature selection, baseline comparison, performance improvement, and "
        "interpretable modelling. Comfortable using Python, pandas, NumPy, "
        "scikit-learn, TensorFlow, and PyTorch for practical analysis and "
        "modelling work. Also has experience turning messy or unstructured inputs "
        "into analysable data through scraping, parsing, and batch processing. "
        "Best aligned with junior data science, applied analytics, research "
        "assistant, and modelling-focused roles where experimentation, structured "
        "reasoning, and data understanding are central."
    ),
    "AI/ML": (
        "Early-career AI and machine learning engineer profile focused on building "
        "practical ML-enabled systems end to end. Experience spans data collection "
        "and processing, model training, evaluation, experimentation, and "
        "supporting tooling around machine learning workflows. Has built ML "
        "projects in audio and music domains, including genre classification and "
        "emotion prediction, and has worked on explainability, representation "
        "learning, and domain adaptation. Also built supporting systems such as a "
        "parser that combines rules and LLM inference to extract structured JSON "
        "from PDFs, and a semantic search/query tool that maps natural language "
        "into structured retrieval. Comfortable with Python ML tooling including "
        "TensorFlow, scikit-learn, PyTorch, pandas, and NumPy. Best aligned with "
        "junior ML engineer, applied AI, AI software, and ML systems roles that "
        "combine software implementation with data and model work."
    ),
}

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

        self.labels = list(PROFILE_TEXTS)
        self.model = SentenceTransformer(model_name)
        self.util = util
        self.profile_embeddings = self.model.encode(
            [PROFILE_TEXTS[label] for label in self.labels],
            normalize_embeddings=True,
        )

    def score_description(self, description):
        description_embedding = self.model.encode(
            description,
            normalize_embeddings=True,
        )
        similarities = self.util.cos_sim(
            description_embedding,
            self.profile_embeddings,
        )[0].tolist()

        profile_scores = dict(zip(self.labels, similarities))
        ranked_profiles = sorted(
            profile_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        top_profile, top_score = ranked_profiles[0]
        second_profile, second_score = ranked_profiles[1]

        return {
            "profile_scores": profile_scores,
            "top_profile": top_profile,
            "top_score": top_score,
            "second_profile": second_profile,
            "second_score": second_score,
            "score_margin": top_score - second_score,
            "fit_summary": format_fit_summary(ranked_profiles, top_score - second_score),
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


def passes_hard_filters(job):
    title = job.get("title", "")
    description = job.get("description", "")
    locations = job.get("locations") or [job.get("location", "")]

    if title_has_hard_reject_term(title, HARD_SENIORITY_TERMS):
        return False

    if title_has_hard_reject_term(title, HARD_COMMERCIAL_TERMS):
        return False

    if not is_uk_location(locations):
        return False

    if has_authorization_mismatch(description):
        return False

    if not passes_experience_filter(description):
        return False

    return True


def score_to_percent(score):
    return max(0, round(score * 100))


def format_fit_summary(ranked_profiles, margin):
    score_parts = [
        f"{label} {score_to_percent(score)}%"
        for label, score in ranked_profiles
    ]
    return f"{' | '.join(score_parts)} | Margin {score_to_percent(margin)}%"


def rank_jobs(jobs):
    matcher = get_profile_matcher()
    ranked_jobs = []

    for job in jobs:
        if not passes_hard_filters(job):
            continue

        score_data = matcher.score_description(job.get("description", ""))
        if score_data["top_score"] < MIN_PROFILE_SCORE:
            continue

        ranked_jobs.append(
            {
                **job,
                **score_data,
            }
        )

    ranked_jobs.sort(
        key=lambda job: (
            job["top_score"],
            job["score_margin"],
            job["second_score"],
            job["title"].lower(),
        ),
        reverse=True,
    )
    return ranked_jobs
