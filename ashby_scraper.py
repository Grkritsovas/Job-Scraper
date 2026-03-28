import requests

from target_config import load_ashby_targets
from utils import (
    HEADERS,
    fetch_job_description,
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


def collect_company_jobs(company, seen_urls):
    jobs = fetch_ashby_jobs(company)
    matches = []
    company_name = normalize_company_name(company)

    for job in jobs:
        title = job.get("title", "")
        job_id = job.get("id")
        url = f"https://jobs.ashbyhq.com/{company}/{job_id}" if job_id else ""

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
                "source": "ashby",
                "target_value": company,
            }
        )
        seen_urls.add(url)

    return matches


def collect_jobs(seen_urls, companies=None):
    matches = []
    for company in get_company_slugs(companies):
        matches.extend(collect_company_jobs(company, seen_urls))
    return matches
