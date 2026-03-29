import unittest
from pathlib import Path

from storage import create_storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/.tmp_storage")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for child in self.test_dir.glob("*"):
            child.unlink()
        self.test_dir.rmdir()

    def test_seen_jobs_are_recipient_aware(self):
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

    def test_load_seen_url_sets_separates_recipient_and_legacy_rows(self):
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

        connection = storage._connect_sqlite()
        try:
            connection.execute(
                """
                INSERT INTO seen_jobs (
                    job_url,
                    source_type,
                    target_value,
                    company_name,
                    title,
                    location
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "https://example.com/job-legacy",
                    "greenhouse",
                    "legacy",
                    "Legacy Co",
                    "Legacy Role",
                    "London",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        seen_sets = storage.load_seen_url_sets("george")

        self.assertEqual(
            {"https://example.com/job-1"},
            seen_sets["recipient_seen_urls"],
        )
        self.assertEqual(
            {"https://example.com/job-legacy"},
            seen_sets["legacy_seen_urls"],
        )


if __name__ == "__main__":
    unittest.main()
