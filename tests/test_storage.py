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
        records = storage.load_recipient_profile_records(enabled_only=False)

        self.assertEqual(1, len(loaded))
        self.assertEqual("george", loaded[0]["id"])
        self.assertEqual("george@example.com", loaded[0]["delivery"]["email"])
        self.assertEqual(2, loaded[0]["job_preferences"]["target_seniority"]["max_explicit_years"])
        self.assertEqual("george", records[0]["recipient_id"])
        self.assertEqual("george@example.com", records[0]["email"])
        self.assertTrue(records[0]["enabled"])

    def test_recipient_profile_versions_can_be_loaded(self):
        db_path = (self.test_dir / "profile_versions.db").resolve()
        storage = create_storage(f"sqlite:///{db_path}")
        storage.ensure_schema()

        first_profile = {
            "id": "demo-recipient",
            "delivery": {"email": "recipient@example.com"},
            "candidate": {
                "summary": "First summary.",
                "target_roles": [{"id": "swe"}],
            },
        }
        second_profile = {
            **first_profile,
            "candidate": {
                "summary": "Second summary.",
                "target_roles": [{"id": "data_science"}],
            },
        }

        storage.upsert_recipient_profile_configs(
            prepare_recipient_profile_db_rows([first_profile])
        )
        storage.upsert_recipient_profile_configs(
            prepare_recipient_profile_db_rows([second_profile])
        )

        versions = storage.load_recipient_profile_versions("demo_recipient")
        loaded_version = storage.load_recipient_profile_version(
            "demo_recipient",
            versions[-1]["version_id"],
        )

        self.assertEqual(2, len(versions))
        self.assertEqual("Second summary.", versions[0]["config"]["candidate"]["summary"])
        self.assertEqual("First summary.", loaded_version["config"]["candidate"]["summary"])

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
                "raw_embedding_score": 0.7 - index / 100,
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
        latest = storage.load_review_audit_rows(
            limit=2,
            recipient_id="recipient-a",
            classification="semantic_above_threshold",
            latest_first=True,
        )
        weakest = storage.load_review_audit_rows(
            limit=2,
            recipient_id="recipient-a",
            classification="semantic_above_threshold",
            sort="semantic_score_asc",
        )
        strongest = storage.load_review_audit_rows(
            limit=2,
            recipient_id="recipient-a",
            classification="semantic_above_threshold",
            sort="semantic_score_desc",
        )
        strongest_raw = storage.load_review_audit_rows(
            limit=2,
            recipient_id="recipient-a",
            classification="semantic_above_threshold",
            sort="raw_embedding_score_desc",
        )
        filter_values = storage.load_review_audit_filter_values()

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
        self.assertAlmostEqual(0.66, loaded[0]["raw_embedding_score"])
        self.assertEqual(
            ["https://example.com/job-6", "https://example.com/job-5"],
            [row["job_url"] for row in latest],
        )
        self.assertEqual(
            ["https://example.com/job-4", "https://example.com/job-5"],
            [row["job_url"] for row in weakest],
        )
        self.assertEqual(
            ["https://example.com/job-6", "https://example.com/job-5"],
            [row["job_url"] for row in strongest],
        )
        self.assertEqual(
            ["https://example.com/job-4", "https://example.com/job-5"],
            [row["job_url"] for row in strongest_raw],
        )
        self.assertEqual(["recipient-a"], filter_values["recipient_ids"])
        self.assertEqual(["semantic"], filter_values["review_families"])

    def test_review_backlog_count_uses_recent_pending_job_state_rows(self):
        db_path = (self.test_dir / "state_backlog.db").resolve()
        storage = create_storage(f"sqlite:///{db_path}")
        storage.ensure_schema()
        rows = [
            {
                "job_url": "https://example.com/semantic-backlog",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Semantic Backlog",
                "location": "London",
                "review_family": "semantic",
                "classification": "semantic_above_threshold_not_reviewed",
                "stage": "semantic_ranking",
                "is_seen": False,
            },
            {
                "job_url": "https://example.com/already-seen",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Already Seen",
                "location": "London",
                "review_family": "semantic",
                "classification": "semantic_above_threshold_seen",
                "stage": "semantic_ranking",
                "is_seen": True,
            },
            {
                "job_url": "https://example.com/gemini-failed",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Gemini Failed",
                "location": "London",
                "review_family": "gemini",
                "classification": "gemini_batch_failed_not_seen",
                "stage": "gemini_pass1",
                "is_seen": False,
            },
            {
                "job_url": "https://example.com/below-threshold",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Below Threshold",
                "location": "London",
                "review_family": "semantic",
                "classification": "semantic_below_threshold",
                "stage": "semantic_ranking",
                "is_seen": True,
            },
            {
                "job_url": "https://example.com/hard-filtered",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Hard Filtered",
                "location": "London",
                "review_family": "hard_filter",
                "classification": "hard_filtered",
                "stage": "hard_filter",
                "is_seen": False,
            },
            {
                "job_url": "https://example.com/recorded-seen",
                "source_type": "ashby",
                "company_name": "Example",
                "title": "Recorded Seen",
                "location": "London",
                "review_family": "gemini",
                "classification": "gemini_pass2_approved_sent_seen",
                "stage": "gemini_pass2",
                "is_seen": True,
            },
        ]
        storage.store_job_state_rows("recipient-a", "run-1", rows)

        self.assertEqual(2, storage.count_recent_pending_job_backlog())
        self.assertEqual(
            {
                "https://example.com/already-seen",
                "https://example.com/below-threshold",
                "https://example.com/recorded-seen",
            },
            storage.load_seen_urls("recipient-a"),
        )

        connection = storage._connect_sqlite()
        try:
            connection.execute(
                """
                UPDATE recipient_seen_jobs
                SET updated_at = '2000-01-01 00:00:00'
                WHERE job_url IN (
                    'https://example.com/semantic-backlog',
                    'https://example.com/gemini-failed'
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(
            0,
            storage.count_recent_pending_job_backlog(max_age_hours=48),
        )


if __name__ == "__main__":
    unittest.main()
