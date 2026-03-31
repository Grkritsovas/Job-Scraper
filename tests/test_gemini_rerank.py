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
        jobs = [make_job(1), make_job(2, title="Graduate Data Analyst")]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science"],
            "semantic_profile_texts": {},
            "negative_profile_texts": ["Senior manager role."],
            "cv_summary": "Strong Python, ML, and data project experience.",
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
            reranked = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=client,
                top_n=2,
                batch_size=10,
            )

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
        self.assertIn('"matched_profile": "Data Science"', second_prompt)
        self.assertIn('"supporting_evidence": [', second_prompt)
        self.assertIn('"batch_fit_score": 84', second_prompt)

    def test_rerank_uses_top_n_and_splits_batches(self):
        jobs = [make_job(index) for index in range(1, 13)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "negative_profile_texts": [],
            "cv_summary": "",
        }
        client = FakeClient(
            [
                {"candidates": []},
                {"candidates": []},
            ]
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            reranked = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=client,
                top_n=11,
                batch_size=10,
            )

        self.assertEqual([], reranked)
        self.assertEqual(2, len(client.models.calls))
        self.assertIn('"url": "https://example.com/job-10"', client.models.calls[0]["contents"])
        self.assertNotIn(
            '"url": "https://example.com/job-11"',
            client.models.calls[0]["contents"],
        )
        self.assertIn('"url": "https://example.com/job-11"', client.models.calls[1]["contents"])
        self.assertNotIn('"url": "https://example.com/job-12"', client.models.calls[1]["contents"])

    def test_rerank_falls_back_to_first_pass_shortlist_if_final_pass_fails(self):
        jobs = [make_job(1)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "negative_profile_texts": [],
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
            reranked = rerank_jobs_with_gemini(
                jobs,
                recipient_profile,
                client=FinalPassFailingClient(),
                top_n=1,
                batch_size=10,
            )

        self.assertEqual(1, len(reranked))
        self.assertEqual("https://example.com/job-1", reranked[0]["url"])
        self.assertEqual(81, reranked[0]["llm_fit_score"])
        self.assertEqual("SWE", reranked[0]["llm_matched_profile"])
        self.assertNotIn("_original_index", reranked[0])

    def test_rerank_returns_top_n_semantic_jobs_when_disabled(self):
        jobs = [make_job(1), make_job(2), make_job(3)]
        recipient_profile = {
            "semantic_profiles": ["swe"],
            "semantic_profile_texts": {},
            "negative_profile_texts": [],
            "cv_summary": "",
        }

        with patch.dict(os.environ, {}, clear=True):
            reranked = rerank_jobs_with_gemini(jobs, recipient_profile, top_n=2)

        self.assertEqual(2, len(reranked))
        self.assertEqual("https://example.com/job-1", reranked[0]["url"])
        self.assertEqual("https://example.com/job-2", reranked[1]["url"])


if __name__ == "__main__":
    unittest.main()
