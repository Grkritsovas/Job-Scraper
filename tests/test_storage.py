import unittest
from pathlib import Path

from config.recipient_profiles import prepare_recipient_profile_db_rows
from storage import create_storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/.tmp_storage")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for child in self.test_dir.glob("*"):
            child.unlink()
        self.test_dir.rmdir()

    def test_recipient_seen_jobs_are_recipient_aware(self):
        db_path = (self.test_dir / "test.db").resolve()
        storage = create_storage(f"sqlite:///{db_path}")
        storage.ensure_schema()
        storage.store_seen_jobs(
            "george",
            [
                {
                    "url": "https://example.com/job-1",
                    "source": "ashby",
                    "target_value": "example",
                    "company": "Example",
                    "title": "Software Engineer",
                    "location": "London",
                }
            ],
        )

        self.assertEqual(
            {"https://example.com/job-1"},
            storage.load_seen_urls("george"),
        )
        self.assertEqual(set(), storage.load_seen_urls("elisabeth"))

    def test_recipient_profile_configs_round_trip(self):
        db_path = (self.test_dir / "profiles.db").resolve()
        storage = create_storage(f"sqlite:///{db_path}")
        storage.ensure_schema()
        rows = prepare_recipient_profile_db_rows(
            [
                {
                    "id": "george",
                    "delivery": {"email": "george@example.com"},
                    "candidate": {
                        "summary": "Strong Python and ML project experience.",
                        "target_roles": [{"id": "swe"}],
                    },
                    "job_preferences": {
                        "target_seniority": {
                            "max_explicit_years": 2,
                            "boost_multiplier": 1.1,
                            "boost_title_terms": ["junior", "graduate"],
                        },
                        "salary": {
                            "preferred_max_gbp": 45000,
                            "hard_cap_gbp": 55000,
                            "penalty_strength": 0.2,
                        },
                    },
                    "eligibility": {
                        "needs_sponsorship": False,
                        "check_hard_eligibility": True,
                        "use_sponsor_lookup": True,
                    },
                    "matching": {
                        "semantic_threshold": 0.5,
                    },
                    "llm_review": {
                        "extra_screening_guidance": ["Prefer early-career roles."],
                        "extra_final_ranking_guidance": ["Prefer clearer evidence."],
                    },
                }
            ]
        )

        storage.upsert_recipient_profile_configs(rows)
        loaded = storage.load_recipient_profile_configs(enabled_only=False)

        self.assertEqual(1, len(loaded))
        self.assertEqual("george", loaded[0]["id"])
        self.assertEqual("george@example.com", loaded[0]["delivery"]["email"])
        self.assertEqual(2, loaded[0]["job_preferences"]["target_seniority"]["max_explicit_years"])

    def test_review_audit_rows_round_trip_and_retention(self):
        db_path = (self.test_dir / "audit.db").resolve()
        storage = create_storage(f"sqlite:///{db_path}")
        storage.ensure_schema()

        rows = [
            {
                "job_url": f"https://example.com/job-{index}",
                "source_type": "ashby",
                "target_value": "example",
                "company_name": "Example",
                "title": f"Job {index}",
                "location": "London",
                "review_family": "semantic",
                "classification": "semantic_above_threshold",
                "stage": "semantic_ranking",
                "semantic_rank": index,
                "semantic_score": 0.5 + index / 100,
                "semantic_threshold": 0.42,
                "supporting_evidence": ["Python"],
                "metadata": {"selected_for_gemini": False},
            }
            for index in range(1, 7)
        ]

        storage.store_review_audit_rows("recipient-a", "run-1", rows)
        deleted = storage.prune_review_audit_rows(keep_rows=3, high_water_rows=5)
        loaded = storage.load_review_audit_rows()

        self.assertEqual(3, deleted)
        self.assertEqual(3, len(loaded))
        self.assertEqual(
            [
                "https://example.com/job-4",
                "https://example.com/job-5",
                "https://example.com/job-6",
            ],
            [row["job_url"] for row in loaded],
        )
        self.assertEqual("recipient-a", loaded[0]["recipient_id"])
        self.assertEqual("run-1", loaded[0]["run_id"])
        self.assertEqual("semantic_above_threshold", loaded[0]["classification"])


if __name__ == "__main__":
    unittest.main()
