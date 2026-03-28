import os

from ashby_scraper import collect_jobs as collect_ashby_jobs
from emailer import send_email
from greenhouse_scraper import collect_jobs as collect_greenhouse_jobs
from lever_scraper import collect_jobs as collect_lever_jobs
from nextjs_scraper import collect_jobs as collect_nextjs_jobs
from storage import create_storage
from target_config import load_configured_targets
from utils import build_digest_bodies


def collect_all_jobs(seen_urls, storage):
    matches = []
    matches.extend(collect_ashby_jobs(seen_urls, storage.load_targets("ashby")))
    matches.extend(
        collect_greenhouse_jobs(seen_urls, storage.load_targets("greenhouse"))
    )
    matches.extend(collect_lever_jobs(seen_urls, storage.load_targets("lever")))
    matches.extend(collect_nextjs_jobs(seen_urls, storage.load_targets("nextjs")))
    return matches


def send_digest(jobs):
    bodies = build_digest_bodies(jobs)
    total = len(jobs)

    for index, body in enumerate(bodies, start=1):
        subject = f"Job digest: {total} new job matches"
        if len(bodies) > 1:
            subject += f" ({index}/{len(bodies)})"
        send_email(subject, body)


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

    seen_urls = storage.load_seen_urls()
    matches = collect_all_jobs(seen_urls, storage)

    if matches:
        send_digest(matches)
        storage.store_seen_jobs(matches)


if __name__ == "__main__":
    main()
