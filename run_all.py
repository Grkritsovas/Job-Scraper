import os

from config.recipient_profiles import load_recipient_profiles
from config.target_config import load_configured_targets
from emailer import send_email
from matching.gemini_rerank import rerank_jobs_with_gemini
from matching.ranking import rank_jobs
from scrapers.ashby_scraper import collect_jobs as collect_ashby_jobs
from scrapers.greenhouse_scraper import collect_jobs as collect_greenhouse_jobs
from scrapers.lever_scraper import collect_jobs as collect_lever_jobs
from scrapers.nextjs_scraper import collect_jobs as collect_nextjs_jobs
from scrapers.scrape_diagnostics import ScrapeDiagnostics
from shared.digest import build_digest_payloads
from sponsorship import enrich_jobs, load_sponsor_company_lookup
from storage import create_storage


def sponsor_aware_profiles(recipient_profiles):
    return any(profile.get("use_sponsor_lookup", False) for profile in recipient_profiles)


def collect_all_jobs(targets, diagnostics):
    seen_urls = set()
    candidates = []
    candidates.extend(
        collect_ashby_jobs(
            seen_urls,
            targets["ashby"],
            diagnostics=diagnostics,
        )
    )
    candidates.extend(
        collect_greenhouse_jobs(
            seen_urls,
            targets["greenhouse"],
            diagnostics=diagnostics,
        )
    )
    candidates.extend(
        collect_lever_jobs(
            seen_urls,
            targets["lever"],
            diagnostics=diagnostics,
        )
    )
    candidates.extend(
        collect_nextjs_jobs(
            seen_urls,
            targets["nextjs"],
            diagnostics=diagnostics,
        )
    )
    return candidates


def select_jobs_for_recipient(candidates, recipient_profile, storage, diagnostics):
    seen_urls = storage.load_seen_urls(recipient_profile["id"])
    unseen_candidates = [
        job for job in candidates if job.get("url") not in seen_urls
    ]
    ranked_jobs, ranking_stats = rank_jobs(
        unseen_candidates,
        recipient_profile,
        return_stats=True,
    )
    review_result = rerank_jobs_with_gemini(ranked_jobs, recipient_profile)
    diagnostics.record_recipient_summary(
        recipient_profile["id"],
        {
            **ranking_stats,
            "input_jobs": len(candidates),
            "seen_skipped_jobs": len(candidates) - len(unseen_candidates),
            "unseen_jobs": len(ranked_jobs),
            "review_mode": review_result["review_mode"],
            "reviewed_jobs": len(review_result["reviewed_jobs"]),
            "llm_shortlisted_jobs": review_result.get("llm_shortlisted_jobs"),
            "gemini_reviewed_jobs": review_result.get("gemini_reviewed_jobs"),
            "review_error": review_result.get("review_error"),
            "recipient_seen_urls": len(seen_urls),
        },
    )
    return review_result


def send_digest(recipient_profile, jobs):
    payloads = build_digest_payloads(jobs, recipient_profile)

    for index, payload in enumerate(payloads, start=1):
        subject = f"Job digest: {len(jobs)} new job matches"
        if len(payloads) > 1:
            subject += f" ({index}/{len(payloads)})"
        send_email(
            subject,
            payload["text"],
            recipient_profile["email"],
            html_body=payload["html"],
        )


def initialize_storage(storage):
    storage.ensure_schema()


def require_database_in_github_actions():
    if os.getenv("GITHUB_ACTIONS") == "true" and not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "GitHub Actions runs require DATABASE_URL so seen jobs persist across runs."
        )


def main():
    require_database_in_github_actions()

    storage = create_storage()
    initialize_storage(storage)
    targets = load_configured_targets()
    diagnostics = ScrapeDiagnostics(
        enabled=os.getenv("JOB_SCRAPER_DIAGNOSTICS", "1") != "0"
    )
    recipient_profiles = load_recipient_profiles()
    sponsor_company_lookup = load_sponsor_company_lookup()
    diagnostics.record_sponsor_lookup_summary(len(sponsor_company_lookup))
    if sponsor_aware_profiles(recipient_profiles) and not sponsor_company_lookup:
        print(
            "Warning: sponsorship-aware recipient profiles are enabled, but no sponsor "
            "company lookup data was loaded."
        )

    candidates = collect_all_jobs(targets, diagnostics)
    enriched_candidates = enrich_jobs(candidates, sponsor_company_lookup)

    for recipient_profile in recipient_profiles:
        review_result = select_jobs_for_recipient(
            enriched_candidates,
            recipient_profile,
            storage,
            diagnostics,
        )
        jobs_to_send = review_result["jobs_to_send"]
        reviewed_jobs = review_result["reviewed_jobs"]
        if jobs_to_send:
            send_digest(recipient_profile, jobs_to_send)
        if reviewed_jobs:
            storage.store_seen_jobs(recipient_profile["id"], reviewed_jobs)


if __name__ == "__main__":
    main()
