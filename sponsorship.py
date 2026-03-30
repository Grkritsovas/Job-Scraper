import csv
import io
import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SPONSOR_CSV_PATHS = [
    BASE_DIR / "sponsor_companies.local.csv",
    BASE_DIR / "data" / "uk_sponsors_companies.csv",
]

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
    normalized = re.sub(r"\b(?:trading\s+as|t\s*/?\s*a)\b.*$", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    parts = normalized.split()
    while parts and parts[-1] in COMPANY_SUFFIXES:
        parts.pop()

    return " ".join(parts)


def _normalize_header(value):
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def _resolve_csv_path(csv_path=None):
    configured = csv_path or os.getenv("SPONSOR_COMPANIES_CSV", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = (BASE_DIR / configured).resolve()
        return path

    for fallback_path in DEFAULT_SPONSOR_CSV_PATHS:
        if fallback_path.exists():
            return fallback_path

    return DEFAULT_SPONSOR_CSV_PATHS[0]


def _extract_company_name(row):
    candidate_keys = [
        "company",
        "company_name",
        "employer",
        "organisation",
        "organization",
        "organisation_name",
        "organization_name",
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


def _read_csv_rows(csv_path=None):
    csv_text = os.getenv("SPONSOR_COMPANIES_CSV_TEXT", "").strip()
    if csv_text:
        reader = csv.DictReader(io.StringIO(csv_text))
        return [{_normalize_header(key): value for key, value in row.items()} for row in reader]

    path = _resolve_csv_path(csv_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        return [{_normalize_header(key): value for key, value in row.items()} for row in reader]


def load_sponsor_company_lookup(csv_path=None):
    rows = _read_csv_rows(csv_path)
    company_lookup = {}

    for row in rows:
        company_name = _extract_company_name(row)
        normalized_company = normalize_company_lookup_name(company_name)
        if not normalized_company or normalized_company in company_lookup:
            continue

        company_lookup[normalized_company] = {
            "company_name": company_name.strip(),
            "town": (row.get("town") or "").strip(),
            "industry": (row.get("industry") or "").strip(),
            "main_tier": (row.get("main_tier") or "").strip(),
            "sub_tier": (row.get("sub_tier") or "").strip(),
        }

    return company_lookup


def resolve_sponsor_company_metadata(normalized_company, sponsor_company_lookup):
    if not normalized_company:
        return {}

    exact_match = sponsor_company_lookup.get(normalized_company)
    if exact_match:
        return exact_match

    if len(normalized_company) < 4:
        return {}

    prefix = normalized_company + " "
    candidate_matches = [
        sponsor_metadata
        for sponsor_company_name, sponsor_metadata in sponsor_company_lookup.items()
        if sponsor_company_name.startswith(prefix)
    ]

    if len(normalized_company) >= 6 and candidate_matches:
        return candidate_matches[0]

    if len(candidate_matches) <= 3:
        return candidate_matches[0] if candidate_matches else {}

    return {}


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
        sponsor_metadata = resolve_sponsor_company_metadata(
            normalized_company,
            sponsor_company_lookup,
        )
        enriched_jobs.append(
            {
                **job,
                "normalized_company": normalized_company,
                "sponsorship_status": classify_sponsorship_status(
                    job.get("title", ""),
                    job.get("description", ""),
                ),
                "is_sponsor_licensed_employer": bool(sponsor_metadata),
                "sponsor_company_metadata": sponsor_metadata,
            }
        )

    return enriched_jobs


def format_sponsorship_summary(job):
    status = (job.get("sponsorship_status") or "unknown").replace("_", " ")
    if status == "unknown":
        return ""

    return "Sponsorship: " + status
