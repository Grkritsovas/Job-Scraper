import csv
import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SPONSOR_CSV = BASE_DIR / "sponsor_companies.local.csv"

COMPANY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "llp",
    "plc",
}

EXPLICIT_YES_PATTERNS = [
    r"\bvisa sponsorship available\b",
    r"\bsponsorship available\b",
    r"\bwe can sponsor\b",
    r"\bwe will sponsor\b",
    r"\boffer visa sponsorship\b",
    r"\bskilled worker visa sponsorship\b",
]

EXPLICIT_NO_PATTERNS = [
    r"\bno sponsorship\b",
    r"\bunable to sponsor\b",
    r"\bcannot sponsor\b",
    r"\bcan'?t sponsor\b",
    r"\bdo not sponsor\b",
    r"\bwill not sponsor\b",
    r"\bno visa support\b",
    r"\bwithout (?:requiring )?(?:visa )?sponsorship\b",
    r"\bunrestricted right to work\b",
    r"\bmust already have (?:the )?right to work\b",
    r"\bmust have (?:the )?right to work\b",
    r"\bmust be authorised to work\b",
    r"\bmust be authorized to work\b",
]

IMPLIED_NO_PATTERNS = [
    r"\bright to work in (?:the )?uk\b",
    r"\blegally authorised to work\b",
    r"\blegally authorized to work\b",
    r"\beligible to work in (?:the )?uk\b",
    r"\bwill you now or in the future require sponsorship\b",
    r"\bnow or in the future require sponsorship\b",
    r"\brequire sponsorship now or in the future\b",
]


def normalize_company_lookup_name(value):
    normalized = (value or "").lower().strip()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    parts = normalized.split()
    while parts and parts[-1] in COMPANY_SUFFIXES:
        parts.pop()

    return " ".join(parts)


def _resolve_csv_path(csv_path=None):
    configured = csv_path or os.getenv("SPONSOR_COMPANIES_CSV", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = (BASE_DIR / configured).resolve()
        return path

    return DEFAULT_SPONSOR_CSV


def _extract_company_name(row):
    candidate_keys = [
        "company",
        "company_name",
        "employer",
        "organisation",
        "organization",
        "name",
    ]

    for key in candidate_keys:
        value = row.get(key)
        if value:
            return value

    for value in row.values():
        if value:
            return value

    return ""


def load_sponsor_company_lookup(csv_path=None):
    path = _resolve_csv_path(csv_path)
    if not path.exists():
        return set()

    normalized_companies = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            company_name = _extract_company_name(row)
            normalized = normalize_company_lookup_name(company_name)
            if normalized:
                normalized_companies.add(normalized)

    return normalized_companies


def classify_sponsorship_status(title, description):
    combined_text = f"{title} {description}".lower()

    if any(re.search(pattern, combined_text) for pattern in EXPLICIT_NO_PATTERNS):
        return "explicit_no"

    if any(re.search(pattern, combined_text) for pattern in EXPLICIT_YES_PATTERNS):
        return "explicit_yes"

    if any(re.search(pattern, combined_text) for pattern in IMPLIED_NO_PATTERNS):
        return "implied_no"

    return "unknown"


def enrich_jobs(jobs, sponsor_company_lookup):
    enriched_jobs = []

    for job in jobs:
        normalized_company = normalize_company_lookup_name(job.get("company", ""))
        enriched_jobs.append(
            {
                **job,
                "normalized_company": normalized_company,
                "sponsorship_status": classify_sponsorship_status(
                    job.get("title", ""),
                    job.get("description", ""),
                ),
                "is_sponsor_licensed_employer": (
                    normalized_company in sponsor_company_lookup
                    if sponsor_company_lookup and normalized_company
                    else False
                ),
            }
        )

    return enriched_jobs


def format_sponsorship_summary(job):
    status = (job.get("sponsorship_status") or "unknown").replace("_", " ")
    parts = [status]

    if job.get("is_sponsor_licensed_employer"):
        parts.append("sponsor-licensed employer")

    return "Sponsorship: " + ", ".join(parts)
