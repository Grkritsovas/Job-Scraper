import requests

from job_urls import sanitize_job_url
from target_config import load_ashby_targets
from utils import (
    HEADERS,
    fetch_job_description_details,
    format_locations,
    is_uk_location,
    normalize_company_name,
)


def get_company_slugs(companies=None):
    if companies is None:
        companies = load_ashby_targets()

    return list(dict.fromkeys(company.lower() for company in companies if company))


def fetch_ashby_jobs(company):
    payload = {
        "operationName": "GetPublicJobListings",
        "variables": {
            "organizationHostedJobsPageName": company,
        },
        "query": """
            query GetPublicJobListings($organizationHostedJobsPageName: String!) {
                jobBoardWithTeams(
                    organizationHostedJobsPageName: $organizationHostedJobsPageName
                ) {
                    jobPostings {
                        id
                        title
                        locationName
                        secondaryLocations {
                            locationName
                        }
                    }
                }
            }
        """,
    }

    try:
        response = requests.post(
            "https://jobs.ashbyhq.com/api/non-user-graphql",
            json=payload,
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        print(f"Failed to fetch Ashby jobs for {company}: {exc}")
        return []

    job_board = data.get("data", {}).get("jobBoardWithTeams")
    if not job_board:
        print(f"No Ashby job board found for {company}: {data}")
        return []

    return job_board.get("jobPostings", [])


def get_job_locations(job):
    secondary_locations = [
        location.get("locationName", "")
        for location in job.get("secondaryLocations") or []
    ]
    return [job.get("locationName", ""), *secondary_locations]


def collect_company_jobs(company, seen_urls, diagnostics=None):
    jobs = fetch_ashby_jobs(company)
    matches = []
    company_name = normalize_company_name(company)
    counts = {
        "fetched_jobs": len(jobs),
        "uk_jobs": 0,
        "url_ok_jobs": 0,
        "new_jobs": 0,
        "description_ok_jobs": 0,
        "html_like_descriptions": 0,
        "usable_jobs": 0,
        "reason": "no_jobs",
        "sample_title": "",
    }

    for job in jobs:
        title = job.get("title", "")
        job_id = job.get("id")
        url = (
            sanitize_job_url(
                f"https://jobs.ashbyhq.com/{company}/{job_id}",
                source="ashby",
                target_value=company,
            )
            if job_id
            else ""
        )

        locations = get_job_locations(job)
        if not is_uk_location(locations):
            continue
        counts["uk_jobs"] += 1

        if not url:
            continue
        counts["url_ok_jobs"] += 1

        if url in seen_urls:
            continue
        counts["new_jobs"] += 1

        description_info = fetch_job_description_details(url)
        description = description_info["description"]
        if not description:
            continue
        counts["description_ok_jobs"] += 1
        if description_info["looks_like_html"]:
            counts["html_like_descriptions"] += 1
            if diagnostics is not None:
                diagnostics.record_description_fallback(
                    "ashby",
                    company,
                    title.strip(),
                    url,
                    description_info["status"],
                    description_info["looks_like_html"],
                )

        matches.append(
            {
                "company": company_name,
                "title": title.strip(),
                "url": url,
                "description": description,
                "locations": locations,
                "location": format_locations(locations),
                "source": "ashby",
                "target_value": company,
                "description_status": description_info["status"],
                "description_looks_like_html": description_info["looks_like_html"],
            }
        )
        seen_urls.add(url)
        counts["usable_jobs"] += 1
        if not counts["sample_title"]:
            counts["sample_title"] = title.strip()

    if counts["fetched_jobs"] and not counts["uk_jobs"]:
        counts["reason"] = "no_uk_jobs"
    elif counts["uk_jobs"] and not counts["url_ok_jobs"]:
        counts["reason"] = "no_valid_urls"
    elif counts["url_ok_jobs"] and not counts["new_jobs"]:
        counts["reason"] = "already_seen_or_duplicate"
    elif counts["new_jobs"] and not counts["description_ok_jobs"]:
        counts["reason"] = "description_fetch_failed"
    elif counts["description_ok_jobs"] and not counts["usable_jobs"]:
        counts["reason"] = "no_usable_jobs"
    elif counts["usable_jobs"]:
        counts["reason"] = "ok"

    if diagnostics is not None:
        diagnostics.record_target_summary("ashby", company, counts)

    return matches


def collect_jobs(seen_urls, companies=None, diagnostics=None):
    matches = []
    for company in get_company_slugs(companies):
        matches.extend(collect_company_jobs(company, seen_urls, diagnostics))
    return matches
