import os

from ashby_scraper import collect_jobs as collect_ashby_jobs
from emailer import send_email
from greenhouse_scraper import collect_jobs as collect_greenhouse_jobs
from lever_scraper import collect_jobs as collect_lever_jobs
from nextjs_scraper import collect_jobs as collect_nextjs_jobs
from recipient_profiles import load_recipient_profiles
from semantic_matching import rank_jobs
from sponsorship import enrich_jobs, load_sponsor_company_lookup
from storage import create_storage
from target_config import load_configured_targets
from utils import build_digest_bodies


def collect_all_jobs(storage):
    seen_urls = set()
    candidates = []
    candidates.extend(collect_ashby_jobs(seen_urls, storage.load_targets("ashby")))
    candidates.extend(
        collect_greenhouse_jobs(seen_urls, storage.load_targets("greenhouse"))
    )
    candidates.extend(collect_lever_jobs(seen_urls, storage.load_targets("lever")))
    candidates.extend(collect_nextjs_jobs(seen_urls, storage.load_targets("nextjs")))
    return candidates


def select_jobs_for_recipient(candidates, recipient_profile, storage):
    seen_urls = storage.load_seen_urls(recipient_profile["id"])
    ranked_jobs = rank_jobs(candidates, recipient_profile)
    return [job for job in ranked_jobs if job["url"] not in seen_urls]


def send_digest(recipient_profile, jobs):
    bodies = build_digest_bodies(jobs, recipient_profile)

    for index, body in enumerate(bodies, start=1):
        subject = f"Job digest: {len(jobs)} new job matches"
        if len(bodies) > 1:
            subject += f" ({index}/{len(bodies)})"
        send_email(subject, body, recipient_profile["email"])


def initialize_storage(storage):
    storage.ensure_schema()
    storage.seed_targets(load_configured_targets())


def require_database_in_github_actions():
    if os.getenv("GITHUB_ACTIONS") == "true" and not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "GitHub Actions runs require DATABASE_URL so seen jobs persist across runs."
        )


def main():
    require_database_in_github_actions()

    storage = create_storage()
    initialize_storage(storage)
    recipient_profiles = load_recipient_profiles()
    sponsor_company_lookup = load_sponsor_company_lookup()

    candidates = collect_all_jobs(storage)
    enriched_candidates = enrich_jobs(candidates, sponsor_company_lookup)

    for recipient_profile in recipient_profiles:
        ranked_jobs = select_jobs_for_recipient(
            enriched_candidates,
            recipient_profile,
            storage,
        )
        if ranked_jobs:
            send_digest(recipient_profile, ranked_jobs)
            storage.store_seen_jobs(recipient_profile["id"], ranked_jobs)


if __name__ == "__main__":
    main()
