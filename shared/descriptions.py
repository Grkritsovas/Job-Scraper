import json
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

MIN_VISIBLE_TEXT_LENGTH = 200
MATCHING_TEXT_SUFFIX_PATTERNS = [
    re.compile(r"\bwhat we offer\b", flags=re.IGNORECASE),
    re.compile(r"\bour benefits\b", flags=re.IGNORECASE),
    re.compile(r"\bemployee benefits\b", flags=re.IGNORECASE),
    re.compile(r"\bbenefits\s+(?:and|&)\s+perks\b", flags=re.IGNORECASE),
    re.compile(r"\bperks\s+(?:and|&)\s+benefits\b", flags=re.IGNORECASE),
    re.compile(r"\bcompensation\s+(?:and|&)\s+benefits\b", flags=re.IGNORECASE),
    re.compile(r"\bbenefits package\b", flags=re.IGNORECASE),
    re.compile(r"\bour culture\b", flags=re.IGNORECASE),
    re.compile(r"\bhow we work\b", flags=re.IGNORECASE),
    re.compile(
        r"\b(?:our\s+)?commitment to diversity,?\s+equity(?:,?\s+and\s+inclusion|,?\s+inclusion)(?:\s+and\s+belonging)?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bdiversity,?\s+equity(?:,?\s+and\s+inclusion|,?\s+inclusion)(?:\s+and\s+belonging)?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\bfraud recruitment disclaimer\b", flags=re.IGNORECASE),
    re.compile(r"\brecruitment fraud\b", flags=re.IGNORECASE),
    re.compile(r"\bequal opportunity employer\b", flags=re.IGNORECASE),
    re.compile(r"\bequal employment opportunity\b", flags=re.IGNORECASE),
    re.compile(r"\breasonable accommodation\b", flags=re.IGNORECASE),
    re.compile(r"\baccommodation for applicants\b", flags=re.IGNORECASE),
    re.compile(
        r"\bwe will ensure that individuals with disabilities are provided reasonable accommodation\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bshould you have any doubts about the authenticity\b",
        flags=re.IGNORECASE,
    ),
]
ROLE_SECTION_START_PATTERNS = [
    re.compile(r"\bthe role,?\s+in a nutshell\b", flags=re.IGNORECASE),
    re.compile(r"\babout the role\b", flags=re.IGNORECASE),
    re.compile(r"\babout this role\b", flags=re.IGNORECASE),
    re.compile(r"\brole overview\b", flags=re.IGNORECASE),
    re.compile(r"\bjob description\b", flags=re.IGNORECASE),
    re.compile(r"\bwhat you(?:['\u2019]ll| will) do\b", flags=re.IGNORECASE),
    re.compile(r"\bwhat you(?:['\u2019]ll| will) be doing\b", flags=re.IGNORECASE),
    re.compile(r"\byour impact\b", flags=re.IGNORECASE),
    re.compile(r"\bkey responsibilities\b", flags=re.IGNORECASE),
    re.compile(r"\bresponsibilities\b", flags=re.IGNORECASE),
    re.compile(r"\brequirements\b", flags=re.IGNORECASE),
    re.compile(r"\bqualifications\b", flags=re.IGNORECASE),
    re.compile(r"\babout you\b", flags=re.IGNORECASE),
    re.compile(r"\bwho you are\b", flags=re.IGNORECASE),
    re.compile(r"\byour experience\b", flags=re.IGNORECASE),
    re.compile(r"\bwhat you(?:['\u2019]ll| will) bring\b", flags=re.IGNORECASE),
    re.compile(r"\bwhat we(?:['\u2019]re| are) looking for\b", flags=re.IGNORECASE),
]
MIN_ROLE_SECTION_LENGTH = 200
MIN_COMPANY_PREFIX_LENGTH = 250


def get_visible_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return soup.get_text(separator=" ", strip=True)


def normalize_text_whitespace(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _has_substantial_prefix(text, cutoff):
    prefix = text[:cutoff].strip()
    if len(prefix) < 40:
        return False

    return len(prefix.split()) >= 6


def strip_matching_boilerplate(text):
    normalized_text = normalize_text_whitespace(text)
    if not normalized_text:
        return ""

    cutoff = len(normalized_text)
    for pattern in MATCHING_TEXT_SUFFIX_PATTERNS:
        match = pattern.search(normalized_text)
        if match and _has_substantial_prefix(normalized_text, match.start()):
            cutoff = min(cutoff, match.start())

    return normalized_text[:cutoff].strip()


def focus_role_matching_text(text):
    normalized_text = normalize_text_whitespace(text)
    if not normalized_text:
        return ""

    role_start = None
    for pattern in ROLE_SECTION_START_PATTERNS:
        match = pattern.search(normalized_text)
        if not match:
            continue
        if match.start() < MIN_COMPANY_PREFIX_LENGTH:
            continue
        if len(normalized_text) - match.start() < MIN_ROLE_SECTION_LENGTH:
            continue
        role_start = (
            match.start()
            if role_start is None
            else min(role_start, match.start())
        )

    if role_start is None:
        return strip_matching_boilerplate(normalized_text)

    return strip_matching_boilerplate(normalized_text[role_start:])


def build_matching_text(title, description):
    normalized_title = normalize_text_whitespace(title)
    cleaned_description = focus_role_matching_text(description)
    parts = []

    if normalized_title:
        parts.append(f"Role title: {normalized_title}")
        parts.append(f"Primary role focus: {normalized_title}")

    if cleaned_description:
        parts.append(cleaned_description)

    return "\n\n".join(parts).strip()


def extract_ashby_description_text(html):
    match = re.search(r'"descriptionHtml":"((?:\\.|[^"])*)"', html)
    if not match:
        return ""

    try:
        description_html = json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return ""

    return get_visible_text(description_html)


def description_looks_like_html(description):
    if not description:
        return False

    lowered = description.lower()
    if "<!doctype" in lowered or "<html" in lowered or "<body" in lowered:
        return True

    return bool(re.search(r"<[a-z!/][^>]*>", description, flags=re.IGNORECASE))


def fetch_job_description_details(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return {
            "description": "",
            "status": "request_failed",
            "looks_like_html": False,
            "length": 0,
        }

    if "jobs.ashbyhq.com" in url:
        ashby_description = extract_ashby_description_text(response.text)
        if len(ashby_description) >= MIN_VISIBLE_TEXT_LENGTH:
            return {
                "description": ashby_description,
                "status": "ashby_description_html",
                "looks_like_html": False,
                "length": len(ashby_description),
            }

    visible_text = get_visible_text(response.text)
    if len(visible_text) >= MIN_VISIBLE_TEXT_LENGTH:
        return {
            "description": visible_text,
            "status": "visible_text",
            "looks_like_html": False,
            "length": len(visible_text),
        }

    looks_like_html = description_looks_like_html(response.text)
    return {
        "description": response.text,
        "status": "raw_html_fallback" if looks_like_html else "raw_text_fallback",
        "looks_like_html": looks_like_html,
        "length": len(response.text),
    }
