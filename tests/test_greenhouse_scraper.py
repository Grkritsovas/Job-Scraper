import unittest
from unittest.mock import patch

from greenhouse_scraper import (
    collect_board_jobs,
    get_greenhouse_job_url,
    normalize_board_token,
)


class GreenhouseScraperTests(unittest.TestCase):
    def test_normalize_board_token_from_embed_url_query(self):
        self.assertEqual(
            "Stripe",
            normalize_board_token(
                "https://boards.greenhouse.io/embed/job_board?for=Stripe&offices%5B%5D=87009"
            ),
        )

    def test_normalize_board_token_from_board_url(self):
        self.assertEqual(
            "dept",
            normalize_board_token("https://job-boards.greenhouse.io/dept?keyword=London"),
        )

    @patch("greenhouse_scraper.get_greenhouse_description")
    @patch("greenhouse_scraper.fetch_greenhouse_jobs")
    def test_ritual_board_can_accept_remote_jobs_without_uk_location(
        self,
        mock_fetch_greenhouse_jobs,
        mock_get_greenhouse_description,
    ):
        mock_fetch_greenhouse_jobs.return_value = [
            {
                "title": "Software Engineer",
                "absolute_url": "https://boards.greenhouse.io/ritual/jobs/123",
                "location": {"name": "Remote"},
                "offices": [],
                "content": "<p>Build things.</p>",
            }
        ]
        mock_get_greenhouse_description.return_value = {
            "description": "Build things.",
            "status": "job_content",
            "looks_like_html": False,
        }

        jobs = collect_board_jobs("ritual", set())

        self.assertEqual(1, len(jobs))
        self.assertEqual("https://boards.greenhouse.io/ritual/jobs/123", jobs[0]["url"])

    def test_relative_greenhouse_job_url_is_expanded(self):
        self.assertEqual(
            "https://boards.greenhouse.io/embed/job_app?token=123",
            get_greenhouse_job_url({"absolute_url": "/embed/job_app?token=123"}),
        )


if __name__ == "__main__":
    unittest.main()
