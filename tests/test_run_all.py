import json
from pathlib import Path
import unittest
from unittest.mock import patch

from run_all import (
    MAX_RECIPIENT_CONCURRENCY,
    RECIPIENT_CONCURRENCY_CAP,
    RUN_SNAPSHOT_SCHEMA_VERSION,
    build_job_state_rows,
    build_run_summary,
    build_run_snapshot,
    collect_all_jobs,
    merge_seen_jobs,
    process_recipient,
    recipient_worker_count,
    select_jobs_for_recipient,
    semantic_below_threshold_seen_jobs,
    write_run_snapshot,
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
    }


class FakeStorage:
    def __init__(self, seen_urls):
        self._seen_urls = set(seen_urls)
        self.stored = []
        self.audit_rows = []

    def load_seen_urls(self, recipient_id):
        return set(self._seen_urls)

    def store_seen_jobs(self, recipient_id, jobs):
        self.stored.append((recipient_id, list(jobs)))

    def store_review_audit_rows(self, recipient_id, run_id, rows):
        self.audit_rows.append((recipient_id, run_id, list(rows)))


class FakeDiagnostics:
    def __init__(self):
        self.calls = []
        self.source_failures = []
        self.recipient_summaries = []

    def record_recipient_summary(self, recipient_id, summary):
        self.calls.append((recipient_id, summary))
        self.recipient_summaries.append({"recipient_id": recipient_id, **summary})

    def record_source_failure(self, source, error):
        self.source_failures.append((source, str(error)))


class RunAllTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/.tmp_run_all")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for child in self.test_dir.glob("*"):
            child.unlink()
        self.test_dir.rmdir()

    def test_collect_all_jobs_dedupes_urls_after_parallel_source_collection(self):
        shared_job = make_job(1)
        ashby_job = {**make_job(2), "source": "ashby", "target_value": "ashby"}
        lever_job = {**make_job(3), "source": "lever", "target_value": "lever"}
        targets = {
            "ashby": ["ashby-company"],
            "greenhouse": ["greenhouse-board"],
            "lever": ["lever-company"],
            "nextjs": ["nextjs-site"],
        }

        with (
            patch(
                "run_all.collect_ashby_jobs",
                return_value=[shared_job, ashby_job],
            ) as ashby_mock,
            patch(
                "run_all.collect_greenhouse_jobs",
                return_value=[shared_job],
            ) as greenhouse_mock,
            patch(
                "run_all.collect_lever_jobs",
                return_value=[lever_job],
            ) as lever_mock,
            patch("run_all.collect_nextjs_jobs", return_value=[]) as nextjs_mock,
        ):
            jobs = collect_all_jobs(targets, diagnostics=None)

        self.assertEqual(
            [
                "https://example.com/job-1",
                "https://example.com/job-2",
                "https://example.com/job-3",
            ],
            [job["url"] for job in jobs],
        )
        for mock in (ashby_mock, greenhouse_mock, lever_mock, nextjs_mock):
            self.assertIsInstance(mock.call_args.args[0], set)

    def test_collect_all_jobs_keeps_successful_sources_when_one_source_fails(self):
        ashby_job = {**make_job(1), "source": "ashby", "target_value": "ashby"}
        lever_job = {**make_job(2), "source": "lever", "target_value": "lever"}
        targets = {
            "ashby": ["ashby-company"],
            "greenhouse": ["greenhouse-board"],
            "lever": ["lever-company"],
            "nextjs": ["nextjs-site"],
        }
        diagnostics = FakeDiagnostics()

        with (
            patch("run_all.collect_ashby_jobs", return_value=[ashby_job]),
            patch(
                "run_all.collect_greenhouse_jobs",
                side_effect=RuntimeError("boom"),
            ),
            patch("run_all.collect_lever_jobs", return_value=[lever_job]),
            patch("run_all.collect_nextjs_jobs", return_value=[]),
        ):
            jobs = collect_all_jobs(targets, diagnostics=diagnostics)

        self.assertEqual(
            ["https://example.com/job-1", "https://example.com/job-2"],
            [job["url"] for job in jobs],
        )
        self.assertEqual([("greenhouse", "boom")], diagnostics.source_failures)

    def test_collect_all_jobs_fails_when_every_source_fails(self):
        targets = {
            "ashby": ["ashby-company"],
            "greenhouse": ["greenhouse-board"],
            "lever": ["lever-company"],
            "nextjs": ["nextjs-site"],
        }
        diagnostics = FakeDiagnostics()

        with (
            patch("run_all.collect_ashby_jobs", side_effect=RuntimeError("ashby")),
            patch(
                "run_all.collect_greenhouse_jobs",
                side_effect=RuntimeError("greenhouse"),
            ),
            patch("run_all.collect_lever_jobs", side_effect=RuntimeError("lever")),
            patch("run_all.collect_nextjs_jobs", side_effect=RuntimeError("nextjs")),
        ):
            with self.assertRaisesRegex(RuntimeError, "All source collection failed"):
                collect_all_jobs(targets, diagnostics=diagnostics)

        self.assertEqual(
            {"ashby", "greenhouse", "lever", "nextjs"},
            {source for source, _error in diagnostics.source_failures},
        )

    def test_select_jobs_for_recipient_skips_seen_urls_before_ranking(self):
        candidates = [make_job(1), make_job(2), make_job(3)]
        recipient_profile = {"id": "george"}
        storage = FakeStorage({"https://example.com/job-2"})
        diagnostics = FakeDiagnostics()

        ranked_jobs = [make_job(1), make_job(3)]
        ranking_stats = {
            "input_jobs": len(ranked_jobs),
            "hard_filtered_jobs": 1,
            "below_threshold_jobs": 0,
            "ranked_jobs": len(ranked_jobs),
            "hard_filter_reasons": {"title_seniority": 1},
        }
        review_result = {
            "jobs_to_send": [make_job(1)],
            "reviewed_jobs": [make_job(1)],
            "review_mode": "gemini",
            "llm_shortlisted_jobs": 1,
            "gemini_reviewed_jobs": 2,
            "review_error": None,
        }

        with (
            patch(
                "run_all.rank_jobs",
                return_value=(ranked_jobs, ranking_stats),
            ) as rank_mock,
            patch(
                "run_all.rerank_jobs_with_gemini",
                return_value=review_result,
            ) as rerank_mock,
        ):
            result = select_jobs_for_recipient(
                candidates,
                recipient_profile,
                storage,
                diagnostics,
            )

        ranked_input_jobs = rank_mock.call_args.args[0]
        self.assertEqual(
            ["https://example.com/job-1", "https://example.com/job-3"],
            [job["url"] for job in ranked_input_jobs],
        )
        rerank_input_jobs = rerank_mock.call_args.args[0]
        self.assertEqual(
            ["https://example.com/job-1", "https://example.com/job-3"],
            [job["url"] for job in rerank_input_jobs],
        )
        self.assertEqual(review_result, result)
        self.assertEqual(1, len(diagnostics.calls))
        recipient_id, summary = diagnostics.calls[0]
        self.assertEqual("george", recipient_id)
        self.assertEqual(3, summary["input_jobs"])
        self.assertEqual(1, summary["seen_skipped_jobs"])
        self.assertEqual(2, summary["ranked_jobs_passed_to_review"])
        self.assertEqual(0, summary["ranked_jobs_not_passed_to_review"])
        self.assertEqual(1, summary["seen_recorded_jobs"])
        self.assertEqual(1, summary["recipient_seen_urls"])

    def test_select_jobs_for_recipient_caps_review_input_with_llm_top_n(self):
        candidates = [make_job(1), make_job(2), make_job(3)]
        recipient_profile = {"id": "george"}
        storage = FakeStorage(set())
        diagnostics = FakeDiagnostics()
        ranked_jobs = [make_job(1), make_job(2), make_job(3)]
        ranking_stats = {
            "input_jobs": len(ranked_jobs),
            "hard_filtered_jobs": 0,
            "below_threshold_jobs": 0,
            "ranked_jobs": len(ranked_jobs),
            "hard_filter_reasons": {},
        }
        review_result = {
            "jobs_to_send": [make_job(1)],
            "reviewed_jobs": [make_job(1)],
            "review_mode": "gemini",
            "llm_shortlisted_jobs": 1,
            "gemini_reviewed_jobs": 1,
            "review_error": None,
        }

        with (
            patch.dict("os.environ", {"JOB_SCRAPER_LLM_TOP_N": "1"}),
            patch(
                "run_all.rank_jobs",
                return_value=(ranked_jobs, ranking_stats),
            ),
            patch(
                "run_all.rerank_jobs_with_gemini",
                return_value=review_result,
            ) as rerank_mock,
        ):
            select_jobs_for_recipient(
                candidates,
                recipient_profile,
                storage,
                diagnostics,
            )

        rerank_input_jobs = rerank_mock.call_args.args[0]
        self.assertEqual(
            ["https://example.com/job-1"],
            [job["url"] for job in rerank_input_jobs],
        )
        summary = diagnostics.calls[0][1]
        self.assertEqual(3, summary["ranked_jobs"])
        self.assertEqual(1, summary["ranked_jobs_passed_to_review"])
        self.assertEqual(2, summary["ranked_jobs_not_passed_to_review"])
        self.assertEqual(1, summary["seen_recorded_jobs"])
        self.assertEqual(0, summary["recipient_seen_urls"])

    def test_select_jobs_for_recipient_marks_semantic_below_threshold_seen(self):
        candidates = [make_job(1), make_job(2), make_job(3)]
        recipient_profile = {"id": "george"}
        storage = FakeStorage(set())
        diagnostics = FakeDiagnostics()
        below_threshold_audit_row = {
            "job_url": "https://example.com/job-2",
            "source_type": "example",
            "target_value": "example",
            "company_name": "Example",
            "title": "Software Engineer 2",
            "location": "London",
            "review_family": "semantic",
            "classification": "semantic_below_threshold",
            "stage": "semantic_ranking",
        }
        hard_filter_audit_row = {
            "job_url": "https://example.com/job-3",
            "source_type": "example",
            "target_value": "example",
            "company_name": "Example",
            "title": "Senior Engineer",
            "location": "London",
            "review_family": "hard_filter",
            "classification": "hard_filtered",
            "stage": "hard_filter",
        }
        ranking_stats = {
            "input_jobs": 3,
            "hard_filtered_jobs": 1,
            "below_threshold_jobs": 1,
            "ranked_jobs": 1,
            "hard_filter_reasons": {"title_seniority": 1},
            "audit_rows": [below_threshold_audit_row, hard_filter_audit_row],
        }
        review_result = {
            "jobs_to_send": [make_job(1)],
            "reviewed_jobs": [make_job(1)],
            "review_mode": "gemini",
            "llm_shortlisted_jobs": 1,
            "gemini_reviewed_jobs": 1,
            "review_error": None,
            "audit_rows": [],
        }

        with (
            patch("run_all.rank_jobs", return_value=([make_job(1)], ranking_stats)),
            patch("run_all.rerank_jobs_with_gemini", return_value=review_result),
        ):
            result = select_jobs_for_recipient(
                candidates,
                recipient_profile,
                storage,
                diagnostics,
            )

        self.assertEqual(
            ["https://example.com/job-1", "https://example.com/job-2"],
            [job["url"] for job in result["seen_jobs"]],
        )
        audit_by_url = {row["job_url"]: row for row in result["audit_rows"]}
        self.assertTrue(audit_by_url["https://example.com/job-2"]["seen_recorded"])
        self.assertFalse(audit_by_url["https://example.com/job-3"].get("seen_recorded", False))

    def test_semantic_below_threshold_seen_jobs_maps_audit_rows(self):
        rows = [
            {
                "job_url": "https://example.com/below",
                "source_type": "ashby",
                "target_value": "example",
                "company_name": "Example",
                "title": "Data Analyst",
                "location": "London",
                "classification": "semantic_below_threshold",
            },
            {
                "job_url": "https://example.com/hard",
                "classification": "hard_filtered",
            },
        ]

        seen_jobs = semantic_below_threshold_seen_jobs(rows)

        self.assertEqual(
            [
                {
                    "url": "https://example.com/below",
                    "source": "ashby",
                    "target_value": "example",
                    "company": "Example",
                    "title": "Data Analyst",
                    "location": "London",
                }
            ],
            seen_jobs,
        )

    def test_build_job_state_rows_tracks_seen_and_pending_states(self):
        rows = [
            {
                "job_url": "https://example.com/below",
                "review_family": "semantic",
                "classification": "semantic_below_threshold",
                "stage": "semantic_ranking",
                "seen_recorded": True,
            },
            {
                "job_url": "https://example.com/backlog",
                "review_family": "semantic",
                "classification": "semantic_above_threshold",
                "stage": "semantic_ranking",
                "seen_recorded": False,
            },
            {
                "job_url": "https://example.com/gemini-failed",
                "review_family": "gemini",
                "classification": "gemini_batch_failed_not_seen",
                "stage": "gemini_pass1",
                "seen_recorded": False,
            },
            {
                "job_url": "https://example.com/hard",
                "review_family": "hard_filter",
                "classification": "hard_filtered",
                "stage": "hard_filter",
            },
        ]

        state_rows = build_job_state_rows(rows)
        state_by_url = {row["job_url"]: row for row in state_rows}

        self.assertEqual(
            {
                "https://example.com/below",
                "https://example.com/backlog",
                "https://example.com/gemini-failed",
            },
            set(state_by_url),
        )
        self.assertTrue(state_by_url["https://example.com/below"]["is_seen"])
        self.assertFalse(state_by_url["https://example.com/backlog"]["is_seen"])
        self.assertEqual(
            "semantic_above_threshold_not_reviewed",
            state_by_url["https://example.com/backlog"]["classification"],
        )
        self.assertEqual(
            "pending_review",
            state_by_url["https://example.com/gemini-failed"]["processing_status"],
        )

    def test_merge_seen_jobs_dedupes_urls(self):
        merged = merge_seen_jobs(
            [make_job(1), make_job(2)],
            [make_job(2), make_job(3)],
        )

        self.assertEqual(
            [
                "https://example.com/job-1",
                "https://example.com/job-2",
                "https://example.com/job-3",
            ],
            [job["url"] for job in merged],
        )

    def test_process_recipient_sends_digest_and_stores_reviewed_jobs(self):
        recipient_profile = {"id": "george", "email": "george@example.com"}
        storage = FakeStorage(set())
        diagnostics = FakeDiagnostics()
        review_result = {
            "jobs_to_send": [make_job(1)],
            "reviewed_jobs": [make_job(1), make_job(2)],
            "review_mode": "gemini",
            "llm_shortlisted_jobs": 1,
            "gemini_reviewed_jobs": 2,
            "review_error": None,
            "audit_rows": [
                {
                    "job_url": "https://example.com/job-1",
                    "review_family": "gemini",
                    "classification": "gemini_pass2_approved_sent_seen",
                    "stage": "gemini_pass2",
                }
            ],
        }

        with (
            patch("run_all.select_jobs_for_recipient", return_value=review_result),
            patch("run_all.send_digest") as send_digest_mock,
        ):
            result = process_recipient(
                recipient_profile,
                [make_job(1), make_job(2)],
                storage,
                diagnostics,
                run_id="test-run",
            )

        self.assertEqual(review_result, result)
        send_digest_mock.assert_called_once_with(
            recipient_profile,
            review_result["jobs_to_send"],
        )
        self.assertEqual(
            [("george", review_result["reviewed_jobs"])],
            storage.stored,
        )
        self.assertEqual(
            [("george", "test-run", review_result["audit_rows"])],
            storage.audit_rows,
        )

    def test_recipient_worker_count_uses_code_cap_and_hard_max(self):
        profiles = [{"id": str(index)} for index in range(10)]

        self.assertEqual(
            min(len(profiles), RECIPIENT_CONCURRENCY_CAP, MAX_RECIPIENT_CONCURRENCY),
            recipient_worker_count(profiles),
        )
        self.assertEqual(1, recipient_worker_count([]))

    def test_build_run_summary_counts_recipient_outcomes(self):
        results = [
            {
                "review_mode": "gemini",
                "jobs_to_send": [make_job(1), make_job(2)],
                "reviewed_jobs": [make_job(1), make_job(2), make_job(3)],
            },
            {
                "review_mode": "gemini_failed",
                "review_error_stage": "batch_screening",
                "jobs_to_send": [],
                "reviewed_jobs": [],
            },
        ]

        summary = build_run_summary(
            candidates=[make_job(1), make_job(2), make_job(3)],
            enriched_candidates=[make_job(1), make_job(2), make_job(3)],
            recipient_profiles=[{"id": "one"}, {"id": "two"}],
            results=results,
        )

        self.assertEqual(3, summary["candidate_jobs"])
        self.assertEqual(2, summary["recipient_count"])
        self.assertEqual(2, summary["jobs_sent"])
        self.assertEqual(3, summary["reviewed_jobs"])
        self.assertEqual({"gemini": 1, "gemini_failed": 1}, summary["review_modes"])
        self.assertEqual(
            {"batch_screening": 1},
            summary["gemini_failure_stages"],
        )

    def test_build_and_write_run_snapshot(self):
        diagnostics = FakeDiagnostics()
        diagnostics.source_failures.append({"source": "greenhouse", "error": "boom"})
        diagnostics.record_recipient_summary(
            "george",
            {
                "review_mode": "gemini",
                "ranked_jobs": 1,
            },
        )
        candidates = [make_job(1)]
        enriched_candidates = [{**make_job(1), "is_sponsor_licensed_employer": True}]
        recipient_profiles = [{"id": "george", "email": "george@example.com"}]
        recipient_results = [
            {
                "review_mode": "gemini",
                "jobs_to_send": [make_job(1)],
                "reviewed_jobs": [make_job(1)],
            }
        ]
        run_summary = build_run_summary(
            candidates,
            enriched_candidates,
            recipient_profiles,
            recipient_results,
        )

        snapshot = build_run_snapshot(
            candidates,
            enriched_candidates,
            recipient_profiles,
            recipient_results,
            run_summary,
            diagnostics,
        )
        output_path = write_run_snapshot(
            self.test_dir / "snapshot.json",
            snapshot,
        )
        saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(RUN_SNAPSHOT_SCHEMA_VERSION, saved["schema_version"])
        self.assertEqual(candidates, saved["candidates"])
        self.assertEqual(enriched_candidates, saved["enriched_candidates"])
        self.assertEqual(recipient_profiles, saved["recipient_profiles"])
        self.assertEqual({"gemini": 1}, saved["run_summary"]["review_modes"])
        self.assertEqual(
            [{"source": "greenhouse", "error": "boom"}],
            saved["source_failures"],
        )


if __name__ == "__main__":
    unittest.main()
