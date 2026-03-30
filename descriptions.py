import json
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

MIN_VISIBLE_TEXT_LENGTH = 200


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
