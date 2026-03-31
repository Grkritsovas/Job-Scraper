import os
import re

from config.config_loader import load_json_config
from matching.profile_library import DEFAULT_SEMANTIC_PROFILES


def _slugify(value):
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return normalized or "recipient"


def _default_profile():
    sender_email = os.getenv("JOB_SCRAPER_EMAIL", "").strip()
    return [
        {
            "id": "default",
            "email": sender_email,
            "semantic_profiles": list(DEFAULT_SEMANTIC_PROFILES),
            "semantic_profile_texts": {},
            "min_top_score": float(os.getenv("JOB_SCRAPER_MIN_SCORE", "0.43")),
            "negative_profile_texts": [],
            "seniority_penalty_weight": float(
                os.getenv("JOB_SCRAPER_SENIORITY_PENALTY_WEIGHT", "0.18")
            ),
            "preferred_salary_max_gbp": None,
            "salary_hard_cap_gbp": None,
            "salary_penalty_max": 0.35,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }
    ]


def _normalize_profile(profile, index):
    recipient_id = profile.get("id") or profile.get("email") or f"recipient_{index + 1}"
    email = (profile.get("email") or os.getenv("JOB_SCRAPER_EMAIL", "")).strip()

    return {
        "id": _slugify(recipient_id),
        "email": email,
        "semantic_profiles": list(
            profile.get("semantic_profiles") or DEFAULT_SEMANTIC_PROFILES
        ),
        "semantic_profile_texts": dict(profile.get("semantic_profile_texts") or {}),
        "min_top_score": float(
            profile.get("min_top_score", os.getenv("JOB_SCRAPER_MIN_SCORE", "0.43"))
        ),
        "negative_profile_texts": list(profile.get("negative_profile_texts") or []),
        "seniority_penalty_weight": float(
            profile.get(
                "seniority_penalty_weight",
                os.getenv("JOB_SCRAPER_SENIORITY_PENALTY_WEIGHT", "0.18"),
            )
        ),
        "preferred_salary_max_gbp": (
            float(profile["preferred_salary_max_gbp"])
            if profile.get("preferred_salary_max_gbp") is not None
            else None
        ),
        "salary_hard_cap_gbp": (
            float(profile["salary_hard_cap_gbp"])
            if profile.get("salary_hard_cap_gbp") is not None
            else None
        ),
        "salary_penalty_max": float(profile.get("salary_penalty_max", 0.35)),
        "care_about_sponsorship": bool(profile.get("care_about_sponsorship", False)),
        "use_sponsor_lookup": bool(profile.get("use_sponsor_lookup", False)),
    }


def load_recipient_profiles():
    configured = load_json_config(
        "RECIPIENT_PROFILES_JSON",
        local_file_name="recipient_profiles.local.json",
        default_value=None,
    )

    if configured is None:
        configured = _default_profile()

    if not isinstance(configured, list):
        raise RuntimeError("Recipient profiles config must be a JSON array.")

    normalized_profiles = [
        _normalize_profile(profile, index)
        for index, profile in enumerate(configured)
    ]

    profile_ids = [profile["id"] for profile in normalized_profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise RuntimeError("Recipient profile ids must be unique.")

    return normalized_profiles
