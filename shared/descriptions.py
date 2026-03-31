import json
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

MIN_VISIBLE_TEXT_LENGTH = 200
MATCHING_TEXT_SUFFIX_PATTERNS = [
    re.compile(
        r"\bour commitment to diversity, equity, inclusion(?:\s+and\s+belonging)?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\bfraud recruitment disclaimer\b", flags=re.IGNORECASE),
    re.compile(r"\bequal employment opportunity\b", flags=re.IGNORECASE),
    re.compile(
        r"\bwe will ensure that individuals with disabilities are provided reasonable accommodation\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bshould you have any doubts about the authenticity\b",
        flags=re.IGNORECASE,
    ),
]


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


def build_matching_text(title, description):
    normalized_title = normalize_text_whitespace(title)
    cleaned_description = strip_matching_boilerplate(description)
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
