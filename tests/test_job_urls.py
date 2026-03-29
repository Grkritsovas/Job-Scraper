import unittest

from job_urls import (
    get_allowed_job_hosts,
    normalize_seed_url,
    sanitize_job_url,
)


class JobUrlTests(unittest.TestCase):
    def test_allowlist_contains_only_known_hosts_for_global_sources(self):
        self.assertEqual({"jobs.ashbyhq.com"}, get_allowed_job_hosts("ashby"))
        self.assertEqual({"jobs.lever.co"}, get_allowed_job_hosts("lever"))
        self.assertEqual(
            {"job-boards.greenhouse.io", "job-boards.eu.greenhouse.io"},
            get_allowed_job_hosts("greenhouse"),
        )

    def test_nextjs_allowlist_includes_target_host_and_known_platform_hosts(self):
        allowed_hosts = get_allowed_job_hosts(
            "nextjs",
            "https://www.multiverse.io/en-GB/careers",
        )

        self.assertIn("www.multiverse.io", allowed_hosts)
        self.assertIn("multiverse.io", allowed_hosts)
        self.assertIn("jobs.ashbyhq.com", allowed_hosts)
        self.assertIn("jobs.lever.co", allowed_hosts)
        self.assertIn("job-boards.greenhouse.io", allowed_hosts)
        self.assertIn("job-boards.eu.greenhouse.io", allowed_hosts)

    def test_sanitize_job_url_strips_tracking_parameters(self):
        cleaned = sanitize_job_url(
            "https://jobs.ashbyhq.com/multiverse/123?utm_source=newsletter&fbclid=test",
            source="ashby",
        )

        self.assertEqual("https://jobs.ashbyhq.com/multiverse/123", cleaned)

    def test_sanitize_job_url_keeps_non_tracking_parameters(self):
        cleaned = sanitize_job_url(
            "https://jobs.lever.co/palantir/123?team=backend&utm_source=newsletter",
            source="lever",
        )

        self.assertEqual("https://jobs.lever.co/palantir/123?team=backend", cleaned)

    def test_rejects_deceptive_subdomain(self):
        cleaned = sanitize_job_url(
            "https://jobs.ashbyhq.com.evil.com/multiverse/123",
            source="ashby",
        )

        self.assertEqual("", cleaned)

    def test_nextjs_rejects_unknown_external_host(self):
        cleaned = sanitize_job_url(
            "https://evil.example/job/123",
            source="nextjs",
            target_value="https://www.multiverse.io/en-GB/careers",
        )

        self.assertEqual("", cleaned)

    def test_nextjs_accepts_known_platform_host(self):
        cleaned = sanitize_job_url(
            "https://jobs.ashbyhq.com/multiverse/123?utm_medium=email",
            source="nextjs",
            target_value="https://www.multiverse.io/en-GB/careers",
        )

        self.assertEqual("https://jobs.ashbyhq.com/multiverse/123", cleaned)

    def test_normalize_seed_url_rejects_malformed_and_cleans_tracking(self):
        self.assertEqual(
            "https://www.multiverse.io/en-GB/careers",
            normalize_seed_url(
                "http://www.multiverse.io/en-GB/careers?utm_source=test#section"
            ),
        )
        self.assertEqual("", normalize_seed_url("javascript:alert('xss')"))


if __name__ == "__main__":
    unittest.main()
