import unittest
from unittest.mock import patch

from scrapers.scrape_diagnostics import ScrapeDiagnostics


class ScrapeDiagnosticsTests(unittest.TestCase):
    def test_source_failure_prints_compact_error_and_is_stored(self):
        diagnostics = ScrapeDiagnostics(enabled=True)

        with patch("builtins.print") as print_mock:
            diagnostics.record_source_failure(
                "greenhouse",
                RuntimeError("503 UNAVAILABLE\nsource outage"),
            )

        self.assertEqual(
            [
                {
                    "source": "greenhouse",
                    "error": "503 UNAVAILABLE source outage",
                }
            ],
            diagnostics.source_failures,
        )
        self.assertEqual(
            '[scrape_failure:greenhouse] error="503 UNAVAILABLE source outage"',
            print_mock.call_args.args[0],
        )

    def test_recipient_summary_prints_compact_review_error_details(self):
        diagnostics = ScrapeDiagnostics(enabled=True)
        long_error = "503 UNAVAILABLE\n" + ("temporary outage " * 20)

        with patch("builtins.print") as print_mock:
            diagnostics.record_recipient_summary(
                "george",
                {
                    "input_jobs": 12,
                    "seen_skipped_jobs": 0,
                    "hard_filtered_jobs": 3,
                    "below_threshold_jobs": 2,
                    "ranked_jobs": 7,
                    "ranked_jobs_passed_to_review": 7,
                    "review_mode": "gemini_failed",
                    "reviewed_jobs": 0,
                    "llm_shortlisted_jobs": 0,
                    "gemini_reviewed_jobs": 0,
                    "review_error_stage": "batch_screening",
                    "review_error": long_error,
                    "recipient_seen_urls": 5,
                    "hard_filter_reasons": {"location": 3},
                },
            )

        line = print_mock.call_args.args[0]
        self.assertIn("review_mode=gemini_failed", line)
        self.assertIn("ranked_jobs_passed_to_review=7", line)
        self.assertIn("review_error_stage=batch_screening", line)
        self.assertIn('review_error="503 UNAVAILABLE temporary outage', line)
        self.assertLess(len(line), 500)

    def test_run_summary_includes_source_failures_and_recipient_outcomes(self):
        diagnostics = ScrapeDiagnostics(enabled=True)
        diagnostics.source_failures.append(
            {
                "source": "greenhouse",
                "error": "503 UNAVAILABLE",
            }
        )

        with patch("builtins.print") as print_mock:
            diagnostics.record_run_summary(
                {
                    "candidate_jobs": 40,
                    "enriched_jobs": 40,
                    "recipient_count": 2,
                    "jobs_sent": 3,
                    "reviewed_jobs": 20,
                    "review_modes": {"gemini": 1, "gemini_failed": 1},
                    "gemini_failure_stages": {"batch_screening": 1},
                }
            )

        line = print_mock.call_args.args[0]
        self.assertIn("[run_summary]", line)
        self.assertIn("candidate_jobs=40", line)
        self.assertIn("jobs_sent=3", line)
        self.assertIn("source_failures=1", line)
        self.assertIn("failed_sources=greenhouse", line)
        self.assertIn("review_modes=gemini:1,gemini_failed:1", line)
        self.assertIn("gemini_failure_stages=batch_screening:1", line)
        self.assertEqual(1, len(diagnostics.run_summaries))


if __name__ == "__main__":
    unittest.main()
