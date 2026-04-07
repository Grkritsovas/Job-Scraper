import unittest
from unittest.mock import patch

from run_all import select_jobs_for_recipient


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

    def load_seen_urls(self, recipient_id):
        return set(self._seen_urls)


class FakeDiagnostics:
    def __init__(self):
        self.calls = []

    def record_recipient_summary(self, recipient_id, summary):
        self.calls.append((recipient_id, summary))


class RunAllTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
