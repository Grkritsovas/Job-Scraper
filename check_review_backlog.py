import argparse
import os

from storage import create_storage


DEFAULT_SUPPORT_BACKLOG_HOURS = 48


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def write_github_output(name, value):
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        print(f"{name}={value}")
        return

    with open(output_path, "a", encoding="utf-8") as output_file:
        output_file.write(f"{name}={value}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Check whether a support scraper run has pending job state backlog."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="SQLite or Postgres database URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=_safe_int(
            os.getenv("JOB_SCRAPER_SUPPORT_BACKLOG_HOURS"),
            DEFAULT_SUPPORT_BACKLOG_HOURS,
        ),
        help="Only count pending job state rows newer than this many hours.",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required to check review backlog.")

    storage = create_storage(args.database_url)
    storage.ensure_schema()
    backlog_count = storage.count_recent_pending_job_backlog(
        max_age_hours=args.max_age_hours,
    )
    should_run = str(backlog_count > 0).lower()

    print(
        "job_state_backlog "
        f"count={backlog_count} "
        f"max_age_hours={args.max_age_hours} "
        f"should_run={should_run}"
    )
    write_github_output("backlog_count", backlog_count)
    write_github_output("should_run", should_run)


if __name__ == "__main__":
    main()
