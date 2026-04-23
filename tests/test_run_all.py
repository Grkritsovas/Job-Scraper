import unittest
from unittest.mock import patch

from run_all import (
    MAX_RECIPIENT_CONCURRENCY,
    RECIPIENT_CONCURRENCY_CAP,
    collect_all_jobs,
    process_recipient,
    recipient_worker_count,
    select_jobs_for_recipient,
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

    def load_seen_urls(self, recipient_id):
        return set(self._seen_urls)

    def store_seen_jobs(self, recipient_id, jobs):
        self.stored.append((recipient_id, list(jobs)))


class FakeDiagnostics:
    def __init__(self):
        self.calls = []

    def record_recipient_summary(self, recipient_id, summary):
        self.calls.append((recipient_id, summary))


class RunAllTests(unittest.TestCase):
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
            patch("run_all.collect_ashby_jobs", return_value=[shared_job, ashby_job]) as ashby_mock,
            patch("run_all.collect_greenhouse_jobs", return_value=[shared_job]) as greenhouse_mock,
            patch("run_all.collect_lever_jobs", return_value=[lever_job]) as lever_mock,
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
            patch("run_all.rank_jobs", return_value=(ranked_jobs, ranking_stats)) as rank_mock,
            patch("run_all.rerank_jobs_with_gemini", return_value=review_result) as rerank_mock,
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
        self.assertEqual(2, summary["unseen_jobs"])
        self.assertEqual(1, summary["recipient_seen_urls"])

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
            )

        self.assertEqual(review_result, result)
        send_digest_mock.assert_called_once_with(recipient_profile, review_result["jobs_to_send"])
        self.assertEqual(
            [("george", review_result["reviewed_jobs"])],
            storage.stored,
        )

    def test_recipient_worker_count_uses_code_cap_and_hard_max(self):
        profiles = [{"id": str(index)} for index in range(10)]

        self.assertEqual(
            min(len(profiles), RECIPIENT_CONCURRENCY_CAP, MAX_RECIPIENT_CONCURRENCY),
            recipient_worker_count(profiles),
        )
        self.assertEqual(1, recipient_worker_count([]))


if __name__ == "__main__":
    unittest.main()
