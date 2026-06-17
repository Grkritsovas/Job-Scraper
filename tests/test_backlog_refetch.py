import unittest
from unittest.mock import patch

import requests

from backlog_refetch import refetch_backlog_job_description


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def long_job_html():
    description = (
        "About the role. Build Python APIs and product features for customers. "
        "Work with backend services, tests, observability, and cross-functional "
        "teammates. "
        * 5
    )
    return f"<html><body><main>{description}</main></body></html>"


class BacklogRefetchTests(unittest.TestCase):
    @patch("backlog_refetch.requests.get")
    def test_ok_page_returns_description_text(self, mock_get):
        mock_get.return_value = FakeResponse(text=long_job_html())

        result = refetch_backlog_job_description(
            "https://example.com/jobs/software-engineer",
        )

        self.assertEqual("ok", result["status"])
        self.assertEqual(200, result["status_code"])
        self.assertIn("Build Python APIs", result["description"])
        mock_get.assert_called_once()

    @patch("backlog_refetch.requests.get")
    def test_404_and_410_are_dead(self, mock_get):
        for status_code in (404, 410):
            with self.subTest(status_code=status_code):
                mock_get.return_value = FakeResponse(
                    status_code=status_code,
                    text="not found",
                )

                result = refetch_backlog_job_description(
                    "https://example.com/jobs/missing",
                )

                self.assertEqual("dead", result["status"])
                self.assertEqual(status_code, result["status_code"])

    @patch("backlog_refetch.requests.get")
    def test_timeout_and_connection_errors_are_temporary(self, mock_get):
        for error in (requests.Timeout("slow"), requests.ConnectionError("offline")):
            with self.subTest(error=error.__class__.__name__):
                mock_get.side_effect = error

                result = refetch_backlog_job_description(
                    "https://example.com/jobs/flaky",
                )

                self.assertEqual("temporary_failure", result["status"])
                self.assertIsNone(result["status_code"])

    @patch("backlog_refetch.requests.get")
    def test_rate_limit_and_5xx_are_temporary(self, mock_get):
        for status_code in (429, 503):
            with self.subTest(status_code=status_code):
                mock_get.return_value = FakeResponse(
                    status_code=status_code,
                    text="try later",
                )

                result = refetch_backlog_job_description(
                    "https://example.com/jobs/flaky",
                )

                self.assertEqual("temporary_failure", result["status"])
                self.assertEqual(status_code, result["status_code"])

    @patch("backlog_refetch.requests.get")
    def test_fetched_page_with_no_usable_text_is_unusable(self, mock_get):
        mock_get.return_value = FakeResponse(
            status_code=200,
            text="<html><body>Short page.</body></html>",
        )

        result = refetch_backlog_job_description(
            "https://example.com/jobs/empty",
        )

        self.assertEqual("unusable", result["status"])
        self.assertEqual("", result["description"])


if __name__ == "__main__":
    unittest.main()
