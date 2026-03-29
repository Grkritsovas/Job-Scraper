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


if __name__ == "__main__":
    unittest.main()
