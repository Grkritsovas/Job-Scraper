import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.replay_run import (
    ReplayStorage,
    filter_profiles,
    load_snapshot,
    run_replay,
    write_digest_previews,
)


def make_job(index):
    return {
        "company": "Example",
        "title": f"Software Engineer {index}",
        "url": f"https://example.com/job-{index}",
        "description": "Build Python APIs.",
        "location": "London",
        "source": "example",
        "target_value": "example",
        "top_profile": "SWE",
        "top_score": 0.72,
        "ranking_score": 0.81,
        "score_margin": 0.12,
    }


class ReplayRunTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/.tmp_replay_run")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for child in self.test_dir.glob("*"):
            child.unlink()
        self.test_dir.rmdir()

    def test_load_snapshot_requires_replay_inputs(self):
        snapshot_path = self.test_dir / "snapshot.json"
        snapshot_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "enriched_candidates"):
            load_snapshot(snapshot_path)

    def test_filter_profiles_reports_missing_recipients(self):
        with self.assertRaisesRegex(RuntimeError, "missing"):
            filter_profiles([{"id": "george"}], ["missing"])

    def test_replay_storage_returns_seen_urls_by_recipient(self):
        storage = ReplayStorage({"george": ["https://example.com/seen"]})

        self.assertEqual(
            {"https://example.com/seen"},
            storage.load_seen_urls("george"),
        )
        self.assertEqual(set(), storage.load_seen_urls("other"))

    def test_run_replay_uses_snapshot_jobs_without_sending_or_storing(self):
        snapshot = {
            "enriched_candidates": [make_job(1), make_job(2)],
            "recipient_profiles": [{"id": "george", "email": "george@example.com"}],
        }
        result = {
            "jobs_to_send": [make_job(1)],
            "reviewed_jobs": [make_job(1), make_job(2)],
            "review_mode": "semantic",
        }

        with (
            patch(
                "tools.replay_run.select_jobs_for_recipient",
                return_value=result,
            ) as select_mock,
            patch("builtins.print"),
        ):
            results = run_replay(
                snapshot,
                snapshot["recipient_profiles"],
                recipient_ids=["george"],
                semantic_only=True,
                top_jobs=1,
            )

        self.assertEqual([(snapshot["recipient_profiles"][0], result)], results)
        self.assertEqual(snapshot["enriched_candidates"], select_mock.call_args.args[0])
        self.assertEqual("george", select_mock.call_args.args[1]["id"])

    def test_run_replay_restores_gemini_key_after_semantic_only(self):
        snapshot = {
            "enriched_candidates": [make_job(1)],
            "recipient_profiles": [{"id": "george", "email": "george@example.com"}],
        }
        result = {
            "jobs_to_send": [],
            "reviewed_jobs": [],
            "review_mode": "semantic",
        }

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "secret"}, clear=True),
            patch("tools.replay_run.select_jobs_for_recipient", return_value=result),
            patch("builtins.print"),
        ):
            run_replay(
                snapshot,
                snapshot["recipient_profiles"],
                semantic_only=True,
            )
            self.assertEqual("secret", os.environ["GEMINI_API_KEY"])

    def test_write_digest_previews_writes_text_and_html(self):
        paths = write_digest_previews(
            self.test_dir,
            {"id": "george", "care_about_sponsorship": False},
            [make_job(1)],
        )

        self.assertEqual(2, len(paths))
        self.assertTrue((self.test_dir / "george.txt").exists())
        self.assertTrue((self.test_dir / "george.html").exists())


if __name__ == "__main__":
    unittest.main()
