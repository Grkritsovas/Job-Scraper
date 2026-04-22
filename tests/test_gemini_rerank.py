import json
import os
import unittest
from unittest.mock import patch

from matching.gemini_rerank import rerank_jobs_with_gemini


def make_job(index, **overrides):
    base = {
        "company": "Example",
        "title": f"Software Engineer {index}",
        "url": f"https://example.com/job-{index}",
        "description": (
            "Build backend APIs in Python and support product features for an "
            "early-career engineering team."
        ),
        "location": "London",
        "top_profile": "SWE",
        "top_score": 0.58,
        "second_profile": "Data Science",
        "second_score": 0.46,
        "ranking_score": 0.58,
        "score_margin": 0.12,
    }
    base.update(overrides)
    return base


class FakeResponse:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class FakeModels:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(
            {
                "model": model,
                "contents": contents,
                "config": config,
            }
        )
        return FakeResponse(self.payloads.pop(0))


class FakeClient:
    def __init__(self, payloads):
        self.models = FakeModels(payloads)


class GeminiRerankTests(unittest.TestCase):
    def test_rerank_uses_profiles_cv_summary_and_two_pass_shortlist(self):
        jobs = [
            make_job(1),
            make_job(
                2,
                title="Graduate Data Analyst",
                salary_upper_bound_gbp=100000.0,
            ),
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science"],
            "semantic_profile_texts": {},
            "cv_summary": "Strong Python, ML, and data project experience.",
            "preferred_salary_max_gbp": 85000.0,
            "salary_hard_cap_gbp": 95000.0,
            "extra_screening_guidance": [
                "Prefer roles explicitly framed as junior or early-career opportunities."
            ],
            "extra_final_ranking_guidance": [
                "Prefer realistic employability over prestige or thematic overlap."
            ],
        }
        client = FakeClient(
            [
                {
                    "candidates": [
                        {
                            "job_url": "https://example.com/job-2",
                            "matched_profile": "Data Science",
                            "fit_score": 84,
                            "why_apply": (
                                "Junior-friendly role with analytical work. "
                                "Your Python and ML experience transfer well."
                            ),
                            "supporting_evidence": [
                                "Graduate Data Analyst",
                                "Build backend APIs in Python",
                            ],
                            "mismatch_evidence": [],
                        }
                    ]
                },
                {
                    "shortlisted_jobs": [
                        {
                            "job_url": "https://example.com/job-2",
                            "fit_score": 88,
                            "why_apply": (
                                "Strong junior data fit with practical analysis work. "
                                "Your Python and ML project experience transfer well."
                            ),
                        }
                    ]
                }
            ]
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=client,
                top_n=2,
                batch_size=10,
            )

        reranked = result["jobs_to_send"]
        self.assertEqual("gemini", result["review_mode"])
        self.assertEqual(2, len(result["reviewed_jobs"]))
        self.assertEqual(1, result["llm_shortlisted_jobs"])
        self.assertEqual(2, result["gemini_reviewed_jobs"])
        self.assertEqual(1, len(reranked))
        self.assertEqual("https://example.com/job-2", reranked[0]["url"])
        self.assertEqual(88, reranked[0]["llm_fit_score"])
        self.assertAlmostEqual(0.88, reranked[0]["ranking_score"])
        self.assertEqual("Data Science", reranked[0]["llm_matched_profile"])
        self.assertIn("Strong junior data fit", reranked[0]["why_apply"])
        self.assertEqual(
            ["Graduate Data Analyst", "Build backend APIs in Python"],
            reranked[0]["supporting_evidence"],
        )

        first_prompt = client.models.calls[0]["contents"]
        second_prompt = client.models.calls[1]["contents"]
        self.assertIn("Strong Python, ML, and data project experience.", first_prompt)
        self.assertIn('"label": "SWE"', first_prompt)
        self.assertIn('"label": "Data Science"', first_prompt)
        self.assertIn('"url": "https://example.com/job-2"', first_prompt)
        self.assertIn('"preferred_salary_max_gbp": 85000.0', first_prompt)
        self.assertIn('"salary_hard_cap_gbp": 95000.0', first_prompt)
        self.assertIn('"salary_upper_bound_gbp": 100000.0', first_prompt)
        self.assertIn(
            "Prefer roles explicitly framed as junior or early-career opportunities.",
            first_prompt,
        )
        self.assertIn('"matched_profile": "Data Science"', second_prompt)
        self.assertIn('"supporting_evidence": [', second_prompt)
        self.assertIn('"batch_fit_score": 84', second_prompt)
        self.assertIn('"salary_upper_bound_gbp": 100000.0', second_prompt)
        self.assertIn(
            "Prefer realistic employability over prestige or thematic overlap.",
            second_prompt,
        )

    def test_rerank_uses_top_n_and_splits_batches(self):
        jobs = [make_job(index) for index in range(1, 13)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }
        client = FakeClient(
            [
                {"candidates": []},
                {"candidates": []},
            ]
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=client,
                top_n=11,
                batch_size=10,
            )

        self.assertEqual("gemini", result["review_mode"])
        self.assertEqual([], result["jobs_to_send"])
        self.assertEqual(11, len(result["reviewed_jobs"]))
        self.assertEqual(0, result["llm_shortlisted_jobs"])
        self.assertEqual(11, result["gemini_reviewed_jobs"])
        self.assertEqual(2, len(client.models.calls))
        self.assertIn('"url": "https://example.com/job-10"', client.models.calls[0]["contents"])
        self.assertNotIn(
            '"url": "https://example.com/job-11"',
            client.models.calls[0]["contents"],
        )
        self.assertIn('"url": "https://example.com/job-11"', client.models.calls[1]["contents"])
        self.assertNotIn('"url": "https://example.com/job-12"', client.models.calls[1]["contents"])

    def test_rerank_returns_no_jobs_if_final_pass_fails(self):
        jobs = [make_job(1)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }

        class FinalPassFailingModels(FakeModels):
            def generate_content(self, model, contents, config):
                self.calls.append(
                    {
                        "model": model,
                        "contents": contents,
                        "config": config,
                    }
                )
                if len(self.calls) == 2:
                    raise RuntimeError("final pass failed")
                return FakeResponse(
                    {
                        "candidates": [
                            {
                                "job_url": "https://example.com/job-1",
                                "matched_profile": "SWE",
                                "fit_score": 81,
                                "why_apply": "Good junior engineering fit.",
                                "supporting_evidence": ["Software Engineer 1"],
                                "mismatch_evidence": [],
                            }
                        ]
                    }
                )

        class FinalPassFailingClient:
            def __init__(self):
                self.models = FinalPassFailingModels([])

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=FinalPassFailingClient(),
                top_n=1,
                batch_size=10,
            )

        self.assertEqual("gemini_failed", result["review_mode"])
        self.assertEqual([], result["jobs_to_send"])
        self.assertEqual([], result["reviewed_jobs"])
        self.assertEqual(0, result["llm_shortlisted_jobs"])
        self.assertEqual(0, result["gemini_reviewed_jobs"])
        self.assertIn("final pass failed", result["review_error"])

    def test_rerank_retries_retryable_batch_failure_and_recovers(self):
        jobs = [make_job(1)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }

        class RetryableBatchModels(FakeModels):
            def generate_content(self, model, contents, config):
                self.calls.append(
                    {
                        "model": model,
                        "contents": contents,
                        "config": config,
                    }
                )
                if len(self.calls) == 1:
                    raise RuntimeError("503 UNAVAILABLE")
                if len(self.calls) == 2:
                    return FakeResponse(
                        {
                            "candidates": [
                                {
                                    "job_url": "https://example.com/job-1",
                                    "matched_profile": "SWE",
                                    "fit_score": 80,
                                    "why_apply": "Good junior engineering fit.",
                                    "supporting_evidence": ["Software Engineer 1"],
                                    "mismatch_evidence": [],
                                }
                            ]
                        }
                    )
                return FakeResponse(
                    {
                        "shortlisted_jobs": [
                            {
                                "job_url": "https://example.com/job-1",
                                "fit_score": 84,
                                "why_apply": "Strong junior engineering fit.",
                            }
                        ]
                    }
                )

        class RetryableBatchClient:
            def __init__(self):
                self.models = RetryableBatchModels([])

        retryable_batch_client = RetryableBatchClient()

        with (
            patch.dict(
                os.environ,
                {
                    "GEMINI_API_KEY": "test-key",
                    "JOB_SCRAPER_LLM_RETRY_ATTEMPTS": "3",
                    "JOB_SCRAPER_LLM_RETRY_BASE_SECONDS": "0",
                },
                clear=True,
            ),
            patch("matching.gemini_rerank.time.sleep") as sleep_mock,
        ):
            result = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=retryable_batch_client,
                top_n=1,
                batch_size=10,
            )

        self.assertEqual("gemini", result["review_mode"])
        self.assertEqual(1, len(result["jobs_to_send"]))
        self.assertEqual(1, len(result["reviewed_jobs"]))
        self.assertEqual(1, result["llm_shortlisted_jobs"])
        self.assertEqual(1, result["gemini_reviewed_jobs"])
        self.assertEqual(3, len(retryable_batch_client.models.calls))
        self.assertEqual(0, sleep_mock.call_count)

    def test_rerank_retries_retryable_final_pass_failure_and_recovers(self):
        jobs = [make_job(1)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }

        class RetryableFinalModels(FakeModels):
            def generate_content(self, model, contents, config):
                self.calls.append(
                    {
                        "model": model,
                        "contents": contents,
                        "config": config,
                    }
                )
                if len(self.calls) == 1:
                    return FakeResponse(
                        {
                            "candidates": [
                                {
                                    "job_url": "https://example.com/job-1",
                                    "matched_profile": "SWE",
                                    "fit_score": 82,
                                    "why_apply": "Good junior engineering fit.",
                                    "supporting_evidence": ["Software Engineer 1"],
                                    "mismatch_evidence": [],
                                }
                            ]
                        }
                    )
                if len(self.calls) == 2:
                    raise RuntimeError("503 UNAVAILABLE")
                return FakeResponse(
                    {
                        "shortlisted_jobs": [
                            {
                                "job_url": "https://example.com/job-1",
                                "fit_score": 86,
                                "why_apply": "Strong junior engineering fit.",
                            }
                        ]
                    }
                )

        class RetryableFinalClient:
            def __init__(self):
                self.models = RetryableFinalModels([])

        retryable_final_client = RetryableFinalClient()

        with (
            patch.dict(
                os.environ,
                {
                    "GEMINI_API_KEY": "test-key",
                    "JOB_SCRAPER_LLM_RETRY_ATTEMPTS": "3",
                    "JOB_SCRAPER_LLM_RETRY_BASE_SECONDS": "0",
                },
                clear=True,
            ),
            patch("matching.gemini_rerank.time.sleep") as sleep_mock,
        ):
            result = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=retryable_final_client,
                top_n=1,
                batch_size=10,
            )

        self.assertEqual("gemini", result["review_mode"])
        self.assertEqual(1, len(result["jobs_to_send"]))
        self.assertEqual(1, len(result["reviewed_jobs"]))
        self.assertEqual(1, result["llm_shortlisted_jobs"])
        self.assertEqual(1, result["gemini_reviewed_jobs"])
        self.assertEqual(3, len(retryable_final_client.models.calls))
        self.assertEqual(0, sleep_mock.call_count)

    def test_rerank_returns_capped_semantic_jobs_when_disabled(self):
        jobs = [make_job(index) for index in range(1, 80)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }

        with patch.dict(os.environ, {}, clear=True):
            result = rerank_jobs_with_gemini(jobs, recipient_profile)

        self.assertEqual("semantic", result["review_mode"])
        self.assertEqual(60, len(result["jobs_to_send"]))
        self.assertEqual(60, len(result["reviewed_jobs"]))
        self.assertEqual("https://example.com/job-1", result["jobs_to_send"][0]["url"])
        self.assertEqual("https://example.com/job-60", result["jobs_to_send"][-1]["url"])

    def test_rerank_honors_semantic_cap_env_var_when_disabled(self):
        jobs = [make_job(index) for index in range(1, 20)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }

        with patch.dict(
            os.environ,
            {"JOB_SCRAPER_MAX_SEMANTIC_EMAIL_JOBS": "7"},
            clear=True,
        ):
            result = rerank_jobs_with_gemini(jobs, recipient_profile)

        self.assertEqual("semantic", result["review_mode"])
        self.assertEqual(7, len(result["jobs_to_send"]))
        self.assertEqual(7, len(result["reviewed_jobs"]))
        self.assertEqual("https://example.com/job-7", result["jobs_to_send"][-1]["url"])

    def test_rerank_only_includes_eligibility_rule_when_hard_eligibility_matters(self):
        jobs = [make_job(1)]
        base_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "cv_summary": "",
        }
        client_false = FakeClient(
            [
                {
                    "candidates": [
                        {
                            "job_url": "https://example.com/job-1",
                            "matched_profile": "SWE",
                            "fit_score": 80,
                            "why_apply": "Good junior engineering fit.",
                            "supporting_evidence": ["Software Engineer 1"],
                            "mismatch_evidence": [],
                        }
                    ]
                },
                {
                    "shortlisted_jobs": [
                        {
                            "job_url": "https://example.com/job-1",
                            "fit_score": 82,
                            "why_apply": "Strong junior engineering fit.",
                        }
                    ]
                },
            ]
        )
        client_true = FakeClient(
            [
                {
                    "candidates": [
                        {
                            "job_url": "https://example.com/job-1",
                            "matched_profile": "SWE",
                            "fit_score": 80,
                            "why_apply": "Good junior engineering fit.",
                            "supporting_evidence": ["Software Engineer 1"],
                            "mismatch_evidence": [],
                        }
                    ]
                },
                {
                    "shortlisted_jobs": [
                        {
                            "job_url": "https://example.com/job-1",
                            "fit_score": 82,
                            "why_apply": "Strong junior engineering fit.",
                        }
                    ]
                },
            ]
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            rerank_jobs_with_gemini(
                jobs,
                {**base_profile, "care_about_hard_eligibility": False},
                client=client_false,
                top_n=1,
                batch_size=10,
            )
            rerank_jobs_with_gemini(
                jobs,
                {**base_profile, "care_about_hard_eligibility": True},
                client=client_true,
                top_n=1,
                batch_size=10,
            )

        false_first_prompt = client_false.models.calls[0]["contents"]
        false_second_prompt = client_false.models.calls[1]["contents"]
        true_first_prompt = client_true.models.calls[0]["contents"]
        true_second_prompt = client_true.models.calls[1]["contents"]

        self.assertNotIn('"eligibility_rule"', false_first_prompt)
        self.assertNotIn('"eligibility_rule"', false_second_prompt)
        self.assertIn('"eligibility_rule"', true_first_prompt)
        self.assertIn('"eligibility_rule"', true_second_prompt)
        self.assertIn("SC clearance", true_first_prompt)
        self.assertIn("SC clearance", true_second_prompt)


if __name__ == "__main__":
    unittest.main()
