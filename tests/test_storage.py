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

    def test_storage_normalizes_quoted_and_spaced_database_url(self):
        storage = create_storage('  "postgresql://example.test/postgres"  ')

        self.assertEqual("postgres", storage.backend)
        self.assertEqual(
            "postgresql://example.test/postgres",
            storage.database_url,
        )


if __name__ == "__main__":
    unittest.main()
