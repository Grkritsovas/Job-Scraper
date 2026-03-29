from urllib.parse import urlparse

import requests

from job_urls import sanitize_job_url
from target_config import load_lever_targets
from utils import (
    HEADERS,
    fetch_job_description,
    format_locations,
    is_uk_location,
    normalize_company_name,
)


LEVER_API_URL = "https://api.lever.co/v0/postings/{site}?mode=json&skip={skip}&limit={limit}"
PAGE_SIZE = 100


def normalize_lever_site(value):
    cleaned = value.strip()
    if "lever.co" not in cleaned:
        return cleaned.strip("/").split("/")[-1]

    parsed = urlparse(cleaned)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return ""

    return path_parts[0]


def load_sites(sites=None):
    if sites is None:
        sites = load_lever_targets()

    return list(
        dict.fromkeys(
            normalized
            for normalized in (normalize_lever_site(value) for value in sites)
            if normalized
        )
    )


def fetch_lever_jobs(site):
    jobs = []
    skip = 0

    while True:
        url = LEVER_API_URL.format(site=site, skip=skip, limit=PAGE_SIZE)
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            batch = response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch Lever jobs for {site}: {exc}")
            return []

        if not batch:
            return jobs

        jobs.extend(batch)
        if len(batch) < PAGE_SIZE:
            return jobs

        skip += PAGE_SIZE


def get_job_locations(job):
    categories = job.get("categories") or {}
    locations = [categories.get("location", "")]

    for value in categories.get("allLocations") or []:
        if isinstance(value, str):
            locations.append(value)

    return locations


def get_job_url(job, site):
    return sanitize_job_url(
        job.get("hostedUrl")
        or job.get("applyUrl")
        or (
            f"https://jobs.lever.co/{site}/{job.get('id')}"
            if job.get("id")
            else ""
        ),
        source="lever",
        target_value=site,
    )


def collect_site_jobs(site, seen_urls):
    jobs = fetch_lever_jobs(site)
    company_name = normalize_company_name(site)
    matches = []

    for job in jobs:
        title = job.get("text", "")
        url = get_job_url(job, site)
        locations = get_job_locations(job)

        if not is_uk_location(locations):
            continue

        if not url or url in seen_urls:
            continue

        description = fetch_job_description(url)
        if not description:
            continue

        matches.append(
            {
                "company": company_name,
                "title": title.strip(),
                "url": url,
                "description": description,
                "locations": locations,
                "location": format_locations(locations),
                "source": "lever",
                "target_value": site,
            }
        )
        seen_urls.add(url)

    return matches


def collect_jobs(seen_urls, sites=None):
    matches = []
    for site in load_sites(sites):
        matches.extend(collect_site_jobs(site, seen_urls))
    return matches
