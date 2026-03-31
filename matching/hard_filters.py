import re

from matching.filters import (
    AUTHORIZATION_MISMATCH_PATTERNS,
    ELIGIBILITY_REJECT_PATTERNS,
    HARD_COMMERCIAL_TERMS,
    HARD_ELIGIBILITY_TITLE_TERMS,
    HARD_SENIORITY_TERMS,
)
from shared.locations import is_uk_location


DEFAULT_MAX_YEARS_EXPERIENCE = 1

EXPERIENCE_PATTERNS = [
    re.compile(r"\b(\d+)\+\s*(?:years?|yrs?|yoe)\b", flags=re.IGNORECASE),
    re.compile(r"\bat least\s+(\d+)\s*(?:years?|yrs?|yoe)\b", flags=re.IGNORECASE),
    re.compile(
        r"\bminimum of\s+(\d+)\s*(?:years?|yrs?|yoe)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\bminimum\s+(\d+)\s*(?:years?|yrs?|yoe)\b", flags=re.IGNORECASE),
    re.compile(
        r"\b(\d+)\s*-\s*(\d+)\s*(?:years?|yrs?|yoe)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d+)\s*to\s*(\d+)\s*(?:years?|yrs?|yoe)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d+)\s*(?:years?|yrs?|yoe)\s+(?:of\s+)?experience\b",
        flags=re.IGNORECASE,
    ),
]


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


def extract_required_experience_years(description):
    if not description:
        return []

    required_years = []
    for pattern in EXPERIENCE_PATTERNS:
        for match in pattern.finditer(description):
            groups = [group for group in match.groups() if group]
            if not groups:
                continue
            required_years.append(int(groups[0]))

    return required_years


def passes_experience_filter(
    description,
    max_years_experience=DEFAULT_MAX_YEARS_EXPERIENCE,
):
    if not description:
        return False

    if max_years_experience is None:
        return True

    return not any(
        years_required > max_years_experience
        for years_required in extract_required_experience_years(description)
    )


def get_hard_filter_reason(
    job,
    max_years_experience=DEFAULT_MAX_YEARS_EXPERIENCE,
):
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

    if not passes_experience_filter(description, max_years_experience):
        return "experience"

    return None


def passes_hard_filters(job, max_years_experience=DEFAULT_MAX_YEARS_EXPERIENCE):
    return get_hard_filter_reason(job, max_years_experience) is None
