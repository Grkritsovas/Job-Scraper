import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.recipient_profiles import load_recipient_profiles
from run_all import select_jobs_for_recipient
from scrapers.scrape_diagnostics import ScrapeDiagnostics
from shared.digest import build_digest_payloads
from storage import create_storage


class ReplayStorage:
    def __init__(self, seen_urls_by_recipient=None):
        self.seen_urls_by_recipient = seen_urls_by_recipient or {}

    def load_seen_urls(self, recipient_id):
        return set(self.seen_urls_by_recipient.get(recipient_id, []))


def load_snapshot(path):
    snapshot_path = Path(path)
    with snapshot_path.open("r", encoding="utf-8") as file_obj:
        snapshot = json.load(file_obj)

    if not isinstance(snapshot, dict):
        raise RuntimeError("Replay snapshot must be a JSON object.")
    if not snapshot.get("enriched_candidates"):
        raise RuntimeError("Replay snapshot is missing enriched_candidates.")
    if not snapshot.get("recipient_profiles"):
        raise RuntimeError("Replay snapshot is missing recipient_profiles.")
    return snapshot


def load_profiles(profile_source, snapshot):
    if profile_source == "snapshot":
        return list(snapshot["recipient_profiles"])

    storage = create_storage()
    storage.ensure_schema()
    return load_recipient_profiles(storage=storage)


def filter_profiles(profiles, recipient_ids):
    if not recipient_ids:
        return list(profiles)

    requested = set(recipient_ids)
    selected = [profile for profile in profiles if profile.get("id") in requested]
    found = {profile.get("id") for profile in selected}
    missing = sorted(requested - found)
    if missing:
        raise RuntimeError(f"Recipient id(s) not found for replay: {', '.join(missing)}")
    return selected


def _temporarily_disable_gemini(semantic_only):
    if not semantic_only:
        return None

    previous = os.environ.pop("GEMINI_API_KEY", None)
    return previous


def _restore_gemini(previous):
    if previous is not None:
        os.environ["GEMINI_API_KEY"] = previous


def _safe_file_stem(value):
    return "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in value
    ).strip("_") or "recipient"


def write_digest_previews(output_dir, recipient_profile, jobs):
    payloads = build_digest_payloads(jobs, recipient_profile)
    if not payloads:
        return []

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_stem = _safe_file_stem(recipient_profile["id"])
    written_paths = []

    for index, payload in enumerate(payloads, start=1):
        suffix = f"_{index}" if len(payloads) > 1 else ""
        text_path = output_path / f"{file_stem}{suffix}.txt"
        html_path = output_path / f"{file_stem}{suffix}.html"
        text_path.write_text(payload["text"], encoding="utf-8")
        html_path.write_text(payload["html"], encoding="utf-8")
        written_paths.extend([text_path, html_path])

    return written_paths


def print_replay_result(recipient_id, result, top_jobs):
    print(
        f"[replay:{recipient_id}] "
        f"review_mode={result.get('review_mode', '-')} "
        f"jobs_to_send={len(result.get('jobs_to_send') or [])} "
        f"reviewed={len(result.get('reviewed_jobs') or [])} "
        f"review_error_stage={result.get('review_error_stage') or '-'}"
    )
    review_error = result.get("review_error")
    if review_error:
        print(f"[replay:{recipient_id}:error] {review_error}")

    for index, job in enumerate((result.get("jobs_to_send") or [])[:top_jobs], start=1):
        score = job.get("ranking_score", job.get("top_score", 0))
        print(
            f"[replay:{recipient_id}:job:{index}] "
            f"score={float(score or 0):.3f} "
            f"company={job.get('company', '-')} "
            f"title={job.get('title', '-')} "
            f"url={job.get('url', '-')}"
        )


def run_replay(
    snapshot,
    profiles,
    recipient_ids=None,
    semantic_only=False,
    preview_dir=None,
    top_jobs=10,
):
    candidates = snapshot["enriched_candidates"]
    selected_profiles = filter_profiles(profiles, recipient_ids or [])
    diagnostics = ScrapeDiagnostics(enabled=True)
    storage = ReplayStorage()
    previous_gemini_key = _temporarily_disable_gemini(semantic_only)
    results = []

    try:
        for recipient_profile in selected_profiles:
            result = select_jobs_for_recipient(
                candidates,
                recipient_profile,
                storage,
                diagnostics,
            )
            results.append((recipient_profile, result))
            print_replay_result(recipient_profile["id"], result, top_jobs)

            if preview_dir:
                written_paths = write_digest_previews(
                    preview_dir,
                    recipient_profile,
                    result.get("jobs_to_send") or [],
                )
                for path in written_paths:
                    print(f"[replay:{recipient_profile['id']}:preview] {path.resolve()}")
    finally:
        _restore_gemini(previous_gemini_key)

    return results


def build_parser():
    parser = argparse.ArgumentParser(
        description="Replay ranking/reranking from a saved run snapshot."
    )
    parser.add_argument("snapshot_path", help="Path produced by run_all.py --save-run.")
    parser.add_argument(
        "--recipient",
        action="append",
        dest="recipient_ids",
        help="Recipient id to replay. Can be provided multiple times.",
    )
    parser.add_argument(
        "--profiles",
        choices=["snapshot", "current-db"],
        default="snapshot",
        help="Use profiles saved in the snapshot or load current DB profiles.",
    )
    parser.add_argument(
        "--semantic-only",
        action="store_true",
        help="Temporarily disable Gemini for this replay process.",
    )
    parser.add_argument(
        "--preview-dir",
        help="Write digest text/html previews for replayed jobs.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of selected jobs to print per recipient.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    snapshot = load_snapshot(args.snapshot_path)
    profiles = load_profiles(args.profiles, snapshot)
    run_replay(
        snapshot,
        profiles,
        recipient_ids=args.recipient_ids,
        semantic_only=args.semantic_only,
        preview_dir=args.preview_dir,
        top_jobs=max(0, args.top),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
