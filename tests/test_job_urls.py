import unittest

from job_urls import (
    get_allowed_job_hosts,
    normalize_seed_url,
    sanitize_job_url,
)


class JobUrlTests(unittest.TestCase):
    def test_allowlist_contains_only_known_hosts_for_global_sources(self):
        self.assertEqual({"jobs.ashbyhq.com"}, get_allowed_job_hosts("ashby"))
        self.assertEqual(
            {"jobs.eu.lever.co", "jobs.lever.co"},
            get_allowed_job_hosts("lever"),
        )
        self.assertEqual(
            {
                "boards.greenhouse.io",
                "job-boards.greenhouse.io",
                "job-boards.eu.greenhouse.io",
            },
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
        self.assertIn("boards.greenhouse.io", allowed_hosts)
        self.assertIn("job-boards.greenhouse.io", allowed_hosts)
        self.assertIn("job-boards.eu.greenhouse.io", allowed_hosts)

    def test_greenhouse_accepts_boards_greenhouse_io(self):
        cleaned = sanitize_job_url(
            "https://boards.greenhouse.io/stripe/jobs/123?gh_src=test&utm_source=mail",
            source="greenhouse",
        )

        self.assertEqual(
            "https://boards.greenhouse.io/stripe/jobs/123?gh_src=test",
            cleaned,
        )

    def test_greenhouse_accepts_company_hosted_job_links_with_gh_jid(self):
        cleaned = sanitize_job_url(
            "https://stripe.com/jobs/search?gh_jid=7532733&utm_source=mail",
            source="greenhouse",
        )

        self.assertEqual(
            "https://stripe.com/jobs/search?gh_jid=7532733",
            cleaned,
        )

    def test_greenhouse_accepts_cockroach_company_hosted_job_links(self):
        cleaned = sanitize_job_url(
            "https://www.cockroachlabs.com/careers/job/?gh_jid=7550343&utm_source=mail",
            source="greenhouse",
        )

        self.assertEqual(
            "https://www.cockroachlabs.com/careers/job/?gh_jid=7550343",
            cleaned,
        )

    def test_greenhouse_accepts_tower_company_hosted_job_links(self):
        cleaned = sanitize_job_url(
            "https://www.tower-research.com/open-positions/?gh_jid=7719159&utm_source=mail",
            source="greenhouse",
        )

        self.assertEqual(
            "https://www.tower-research.com/open-positions/?gh_jid=7719159",
            cleaned,
        )

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

    def test_sanitize_job_url_accepts_eu_lever_host(self):
        cleaned = sanitize_job_url(
            "https://jobs.eu.lever.co/flock/123?location=London&utm_source=newsletter",
            source="lever",
        )

        self.assertEqual(
            "https://jobs.eu.lever.co/flock/123?location=London",
            cleaned,
        )

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
