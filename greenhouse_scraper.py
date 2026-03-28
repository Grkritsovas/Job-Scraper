import html
from urllib.parse import urlparse

import requests

from target_config import load_greenhouse_targets
from utils import (
    HEADERS,
    format_locations,
    get_visible_text,
    is_engineering_role,
    is_relevant_title,
    is_uk_location,
    normalize_company_name,
    passes_experience_filter,
)


GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"


def normalize_board_token(value):
    cleaned = value.strip()
    if "greenhouse.io" not in cleaned:
        return cleaned.strip("/").split("/")[-1]

    parsed = urlparse(cleaned)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return ""

    return path_parts[0]


def load_board_tokens(board_tokens=None):
    if board_tokens is None:
        board_tokens = load_greenhouse_targets()

    return list(
        dict.fromkeys(
            normalized
            for normalized in (normalize_board_token(value) for value in board_tokens)
            if normalized
        )
    )


def fetch_greenhouse_jobs(board_token):
    url = GREENHOUSE_API_URL.format(board_token=board_token)

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        print(f"Failed to fetch Greenhouse jobs for {board_token}: {exc}")
        return []

    return data.get("jobs", [])


def get_greenhouse_locations(job):
    locations = [job.get("location", {}).get("name", "")]

    for office in job.get("offices") or []:
        office_location = office.get("location", "")
        if office_location:
            locations.append(office_location)

    return locations


def get_greenhouse_description(job):
    content = html.unescape(job.get("content", ""))
    if not content:
        return ""

    return get_visible_text(content)


def collect_board_jobs(board_token, seen_urls):
    jobs = fetch_greenhouse_jobs(board_token)
    company_name = normalize_company_name(board_token)
    matches = []

    for job in jobs:
        title = job.get("title", "")
        url = job.get("absolute_url", "")
        locations = get_greenhouse_locations(job)
        location_candidates = [*locations, title]

        if not is_relevant_title(title):
            continue

        if not is_uk_location(location_candidates):
            continue

        if not url or url in seen_urls:
            continue

        description = get_greenhouse_description(job)
        if not description:
            continue

        if not is_engineering_role(title, description):
            continue

        if not passes_experience_filter(description):
            continue

        matches.append(
            {
                "company": company_name,
                "title": title.strip(),
                "url": url,
                "location": format_locations(locations),
                "source": "greenhouse",
                "target_value": board_token,
            }
        )
        seen_urls.add(url)

    return matches


def collect_jobs(seen_urls, board_tokens=None):
    matches = []
    for board_token in load_board_tokens(board_tokens):
        matches.extend(collect_board_jobs(board_token, seen_urls))
    return matches
