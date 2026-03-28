import json

import requests
from bs4 import BeautifulSoup

from target_config import load_nextjs_targets
from utils import (
    HEADERS,
    fetch_job_description,
    format_locations,
    get_company_name_from_url,
    is_engineering_role,
    is_relevant_title,
    passes_experience_filter,
)


def load_urls(urls=None):
    if urls is not None:
        return list(dict.fromkeys(url for url in urls if url))

    return load_nextjs_targets()


def fetch_nextjs_data(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script or not script.string:
        raise ValueError(f"No __NEXT_DATA__ block found for {url}")

    return json.loads(script.string)


def extract_jobs(data):
    page_props = data.get("props", {}).get("pageProps", {})
    return page_props.get("jobPostings", [])


def get_job_url(job):
    return (
        job.get("applyUrl")
        or job.get("url")
        or job.get("applyLink")
        or job.get("externalLink")
        or ""
    )


def get_job_locations(job):
    return [
        job.get("location", ""),
        job.get("locationName", ""),
        job.get("jobLocation", ""),
    ]


def collect_url_jobs(url, seen_urls):
    data = fetch_nextjs_data(url)
    jobs = extract_jobs(data)
    company_name = get_company_name_from_url(url)
    matches = []

    for job in jobs:
        title = job.get("title", "")
        job_url = get_job_url(job)

        if not is_relevant_title(title):
            continue

        if not job_url or job_url in seen_urls:
            continue

        description = fetch_job_description(job_url)
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
                "url": job_url,
                "location": format_locations(get_job_locations(job)),
                "source": "nextjs",
                "target_value": url,
            }
        )
        seen_urls.add(job_url)

    return matches


def collect_jobs(seen_urls, urls=None):
    matches = []
    for url in load_urls(urls):
        matches.extend(collect_url_jobs(url, seen_urls))
    return matches
