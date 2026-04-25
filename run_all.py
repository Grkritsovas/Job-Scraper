import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path

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

RECIPIENT_CONCURRENCY_CAP = 4
MAX_RECIPIENT_CONCURRENCY = 8
SOURCE_FAMILY_CONCURRENCY = 4
RUN_SNAPSHOT_SCHEMA_VERSION = 1


def build_parser():
    parser = argparse.ArgumentParser(
        description="Scrape, rank, optionally rerank, and send job digests."
    )
    parser.add_argument(
        "--save-run",
        help=(
            "Write a local JSON replay snapshot after the run. "
            "The snapshot can include job descriptions and candidate summaries."
        ),
    )
    return parser


def sponsor_aware_profiles(recipient_profiles):
    return any(profile.get("use_sponsor_lookup", False) for profile in recipient_profiles)


def collect_all_jobs(targets, diagnostics):
    source_collectors = [
        (
            "ashby",
            lambda: collect_ashby_jobs(
                set(),
                targets["ashby"],
                diagnostics=diagnostics,
            ),
        ),
        (
            "greenhouse",
            lambda: collect_greenhouse_jobs(
                set(),
                targets["greenhouse"],
                diagnostics=diagnostics,
            ),
        ),
        (
            "lever",
            lambda: collect_lever_jobs(
                set(),
                targets["lever"],
                diagnostics=diagnostics,
            ),
        ),
        (
            "nextjs",
            lambda: collect_nextjs_jobs(
                set(),
                targets["nextjs"],
                diagnostics=diagnostics,
            ),
        ),
    ]

    collected_by_source = {}
    failed_sources = []
    with ThreadPoolExecutor(
        max_workers=min(SOURCE_FAMILY_CONCURRENCY, len(source_collectors))
    ) as executor:
        future_by_source = {
            executor.submit(collector): source_name
            for source_name, collector in source_collectors
        }
        for future in as_completed(future_by_source):
            source_name = future_by_source[future]
            try:
                collected_by_source[source_name] = future.result()
            except Exception as exc:
                failed_sources.append(source_name)
                if diagnostics is not None:
                    diagnostics.record_source_failure(source_name, exc)

    if failed_sources and not collected_by_source:
        raise RuntimeError(
            "All source collection failed: "
            + ", ".join(sorted(failed_sources))
        )

    merged_candidates = []
    seen_urls = set()
    for source_name, _collector in source_collectors:
        for job in collected_by_source.get(source_name) or []:
            job_url = job.get("url")
            if not job_url or job_url in seen_urls:
                continue
            seen_urls.add(job_url)
            merged_candidates.append(job)

    return merged_candidates


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
            "review_error_stage": review_result.get("review_error_stage"),
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


def recipient_worker_count(recipient_profiles):
    if not recipient_profiles:
        return 1

    configured = max(1, min(RECIPIENT_CONCURRENCY_CAP, MAX_RECIPIENT_CONCURRENCY))
    return min(len(recipient_profiles), configured)


def process_recipient(recipient_profile, candidates, storage, diagnostics):
    review_result = select_jobs_for_recipient(
        candidates,
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
    return review_result


def process_recipients(recipient_profiles, candidates, storage, diagnostics):
    worker_count = recipient_worker_count(recipient_profiles)
    if worker_count == 1:
        return [
            process_recipient(
                recipient_profile,
                candidates,
                storage,
                diagnostics,
            )
            for recipient_profile in recipient_profiles
        ]

    recipient_results = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_by_recipient_id = {
            executor.submit(
                process_recipient,
                recipient_profile,
                candidates,
                storage,
                diagnostics,
            ): recipient_profile["id"]
            for recipient_profile in recipient_profiles
        }
        for future in as_completed(future_by_recipient_id):
            recipient_id = future_by_recipient_id[future]
            try:
                recipient_results.append(future.result())
            except Exception as exc:
                raise RuntimeError(
                    f"Recipient processing failed for {recipient_id}: {exc}"
                ) from exc

    return recipient_results


def build_run_summary(candidates, enriched_candidates, recipient_profiles, results):
    review_modes = Counter(
        result.get("review_mode", "unknown") for result in results
    )
    gemini_failure_stages = Counter(
        result.get("review_error_stage") or "unknown"
        for result in results
        if result.get("review_mode") == "gemini_failed"
    )

    return {
        "candidate_jobs": len(candidates),
        "enriched_jobs": len(enriched_candidates),
        "recipient_count": len(recipient_profiles),
        "jobs_sent": sum(len(result.get("jobs_to_send") or []) for result in results),
        "reviewed_jobs": sum(
            len(result.get("reviewed_jobs") or []) for result in results
        ),
        "review_modes": dict(review_modes),
        "gemini_failure_stages": dict(gemini_failure_stages),
    }


def build_run_snapshot(
    candidates,
    enriched_candidates,
    recipient_profiles,
    recipient_results,
    run_summary,
    diagnostics,
):
    return {
        "schema_version": RUN_SNAPSHOT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidates": candidates,
        "enriched_candidates": enriched_candidates,
        "recipient_profiles": recipient_profiles,
        "recipient_results": recipient_results,
        "recipient_summaries": list(
            getattr(diagnostics, "recipient_summaries", [])
        ),
        "source_failures": list(getattr(diagnostics, "source_failures", [])),
        "run_summary": run_summary,
    }


def write_run_snapshot(path, snapshot):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return output_path


def main(argv=None):
    args = build_parser().parse_args(argv)
    require_database_in_github_actions()

    storage = create_storage()
    initialize_storage(storage)
    targets = load_configured_targets()
    diagnostics = ScrapeDiagnostics(
        enabled=os.getenv("JOB_SCRAPER_DIAGNOSTICS", "1") != "0"
    )
    recipient_profiles = load_recipient_profiles(storage=storage)
    sponsor_company_lookup = load_sponsor_company_lookup()
    diagnostics.record_sponsor_lookup_summary(len(sponsor_company_lookup))
    if sponsor_aware_profiles(recipient_profiles) and not sponsor_company_lookup:
        print(
            "Warning: sponsorship-aware recipient profiles are enabled, but no sponsor "
            "company lookup data was loaded."
        )

    candidates = collect_all_jobs(targets, diagnostics)
    enriched_candidates = enrich_jobs(candidates, sponsor_company_lookup)

    recipient_results = process_recipients(
        recipient_profiles,
        enriched_candidates,
        storage,
        diagnostics,
    )
    run_summary = build_run_summary(
        candidates,
        enriched_candidates,
        recipient_profiles,
        recipient_results,
    )
    diagnostics.record_run_summary(run_summary)

    if args.save_run:
        output_path = write_run_snapshot(
            args.save_run,
            build_run_snapshot(
                candidates,
                enriched_candidates,
                recipient_profiles,
                recipient_results,
                run_summary,
                diagnostics,
            ),
        )
        print(f"[run_snapshot] path={output_path.resolve()}")


if __name__ == "__main__":
    main()
