import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from sponsorship import format_sponsorship_summary


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

MIN_VISIBLE_TEXT_LENGTH = 200

EXPERIENCE_PATTERNS = [
    r"\b[2-9]\+\s*(?:years?|yrs?|yoe)\b",
    r"\b10\+\s*(?:years?|yrs?|yoe)\b",
    r"\bat least\s+[2-9]\s*(?:years?|yrs?|yoe)\b",
    r"\bat least\s+10\s*(?:years?|yrs?|yoe)\b",
    r"\bminimum of\s+[2-9]\s*(?:years?|yrs?|yoe)\b",
    r"\bminimum of\s+10\s*(?:years?|yrs?|yoe)\b",
    r"\bminimum\s+[2-9]\s*(?:years?|yrs?|yoe)\b",
    r"\bminimum\s+10\s*(?:years?|yrs?|yoe)\b",
    r"\b[2-9]\s*-\s*\d+\s*(?:years?|yrs?|yoe)\b",
    r"\b10\s*-\s*\d+\s*(?:years?|yrs?|yoe)\b",
    r"\b[2-9]\s*to\s*\d+\s*(?:years?|yrs?|yoe)\b",
    r"\b10\s*to\s*\d+\s*(?:years?|yrs?|yoe)\b",
    r"\b[2-9]\s*(?:years?|yrs?|yoe)\s+(?:of\s+)?experience\b",
    r"\b10\s*(?:years?|yrs?|yoe)\s+(?:of\s+)?experience\b",
]

UK_LOCATION_TERMS = {
    "aberdeen",
    "bath",
    "basingstoke",
    "blackburn",
    "blackpool",
    "birmingham",
    "bournemooth",
    "bournemouth",
    "bristol",
    "cambridge",
    "cardif",
    "cardiff",
    "cheltenham",
    "coventry",
    "crawley",
    "crawly",
    "darlington",
    "devon",
    "doncaster",
    "dorchester",
    "dumfries",
    "edinburgh",
    "edingburgh",
    "exeter",
    "falkirk",
    "farnborough",
    "farnham",
    "galashiels",
    "glasgow",
    "guildford",
    "harrow",
    "hinckley",
    "horsham",
    "hull",
    "inverness",
    "isle of wight",
    "kent",
    "kilmarnock",
    "kingston upon thames",
    "lancashire",
    "lancaster",
    "leeds",
    "leicester",
    "london",
    "maidstone",
    "manchester",
    "middlesborough",
    "middlesbrough",
    "newcastle",
    "newport",
    "oldham",
    "oxford",
    "oxfordshire",
    "perth",
    "plymouth",
    "portsmouth",
    "reading",
    "redhill",
    "scotland",
    "sheffield",
    "shefield",
    "slough",
    "somerset",
    "southampton",
    "stockport",
    "stockton-on-tees",
    "surrey",
    "swindon",
    "taunton",
    "teesside",
    "torquay",
    "truro",
    "warwick",
    "west midlands",
    "weybridge",
    "woking",
    "york",
}


def normalize_company_name(value):
    cleaned = value.replace(".com", "").replace(".io", "")
    cleaned = cleaned.replace("-", " ").replace(".", " ").strip()
    return " ".join(part.capitalize() for part in cleaned.split()) or value


def get_company_name_from_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    host = host.split(":", 1)[0]
    host_parts = host.split(".")
    label = host_parts[0]

    if label in {"careers", "jobs", "apply", "work", "join"} and len(host_parts) > 1:
        label = host_parts[1]

    return normalize_company_name(label)


def get_visible_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return soup.get_text(separator=" ", strip=True)


def extract_ashby_description_text(html):
    match = re.search(r'"descriptionHtml":"((?:\\.|[^"])*)"', html)
    if not match:
        return ""

    try:
        description_html = json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return ""

    return get_visible_text(description_html)


def fetch_job_description(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    if "jobs.ashbyhq.com" in url:
        ashby_description = extract_ashby_description_text(response.text)
        if len(ashby_description) >= MIN_VISIBLE_TEXT_LENGTH:
            return ashby_description

    visible_text = get_visible_text(response.text)
    if len(visible_text) >= MIN_VISIBLE_TEXT_LENGTH:
        return visible_text

    return response.text


def is_uk_location(locations):
    if isinstance(locations, str):
        locations = [locations]

    bad_keywords = [
        "hop",
        "warehouse",
        "trading estate",
        "rider",
        "delivery",
        "store",
        "kitchen",
        "site",
    ]

    country_level_uk_patterns = [
        r"\buk\b",
        r"united kingdom",
        r"\bgb\b",
        r"remote\s*\(uk\)",
        r"\bengland\b",
        r"\bscotland\b",
    ]

    foreign_keywords = [
        "united states",
        "usa",
        "canada",
        "australia",
        "ukraine",
        "brazil",
        "mexico",
        "new york",
        "serbia",
        "germany",
        "romania",
        "cyprus",
        "switzerland",
        "portugal",
        "lithuania",
        "czech republic",
        "poland",
        "spain",
        "france",
        "italy",
        "ireland",
        "belgrade",
        "berlin",
        "sydney",
        "new south wales",
    ]

    for location in locations:
        if not location:
            continue

        normalized = location.lower()

        if any(keyword in normalized for keyword in bad_keywords):
            continue

        if any(re.search(pattern, normalized) for pattern in country_level_uk_patterns):
            return True

        if any(keyword in normalized for keyword in foreign_keywords):
            continue

        if any(_contains_location_term(normalized, location_term) for location_term in UK_LOCATION_TERMS):
            return True

    return False


def _contains_location_term(location_text, location_term):
    pattern = r"(?<![a-z])" + re.escape(location_term).replace(r"\ ", r"\s+") + r"(?![a-z])"
    return re.search(pattern, location_text) is not None


def passes_experience_filter(description):
    if not description:
        return False

    return not any(
        re.search(pattern, description, flags=re.IGNORECASE)
        for pattern in EXPERIENCE_PATTERNS
    )


def is_engineering_role(title, description):
    text = f"{title} {description}".lower()

    engineering_keywords = [
        "engineer",
        "developer",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "data engineer",
    ]

    return any(keyword in text for keyword in engineering_keywords)


def dedupe_keep_order(values):
    return list(dict.fromkeys(value for value in values if value))


def format_locations(locations):
    unique_locations = dedupe_keep_order(locations)
    return ", ".join(unique_locations)


def format_company_heading(company, company_jobs, recipient_profile):
    sponsorship_enabled = (
        recipient_profile.get("care_about_sponsorship", False)
        or recipient_profile.get("use_sponsor_lookup", False)
    )
    if not sponsorship_enabled:
        return company

    if any(job.get("is_sponsor_licensed_employer") for job in company_jobs):
        return f"{company} [Sponsor-licensed]"

    return company


def build_digest_bodies(jobs, recipient_profile, max_jobs_per_email=20):
    if not jobs:
        return []

    jobs_by_company = {}
    for job in jobs:
        jobs_by_company.setdefault(job["company"], []).append(job)

    company_blocks = []
    sorted_companies = sorted(
        jobs_by_company,
        key=lambda company: (
            max(
                job.get("ranking_score", job.get("top_score", 0))
                for job in jobs_by_company[company]
            ),
            company.lower(),
        ),
        reverse=True,
    )
    for company in sorted_companies:
        company_jobs = sorted(
            jobs_by_company[company],
            key=lambda job: (
                job.get("ranking_score", job.get("top_score", 0)),
                job.get("top_score", 0),
                job.get("score_margin", 0),
                job["title"].lower(),
                job["url"].lower(),
            ),
            reverse=True,
        )
        lines = [format_company_heading(company, company_jobs, recipient_profile)]
        for job in company_jobs:
            location = job.get("location", "")
            location_suffix = f" | {location}" if location else ""
            lines.append(f"- {job['title']}{location_suffix}")
            if job.get("fit_summary"):
                lines.append(f"  Top fit: {job['fit_summary']}")
            if (
                recipient_profile.get("care_about_sponsorship", False)
                or recipient_profile.get("use_sponsor_lookup", False)
            ):
                lines.append(f"  {format_sponsorship_summary(job)}")
            lines.append(job["url"])
        company_blocks.append((len(company_jobs), "\n".join(lines)))

    bodies = []
    current_blocks = []
    current_count = 0

    for block_count, block_text in company_blocks:
        if current_blocks and current_count + block_count > max_jobs_per_email:
            bodies.append("\n\n".join(current_blocks))
            current_blocks = []
            current_count = 0

        current_blocks.append(block_text)
        current_count += block_count

    if current_blocks:
        bodies.append("\n\n".join(current_blocks))

    return bodies
