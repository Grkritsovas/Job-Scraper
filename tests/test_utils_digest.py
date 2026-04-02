import unittest

from utils import build_digest_bodies, build_digest_html_bodies


class DigestFormattingTests(unittest.TestCase):
    def test_company_heading_shows_sponsor_marker_for_opted_in_recipient(self):
        jobs = [
            {
                "company": "Marshmallow",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "SWE",
                "ranking_score": 0.54,
                "top_score": 0.54,
                "second_profile": "AI/ML",
                "second_score": 0.30,
                "score_margin": 0.10,
                "is_sponsor_licensed_employer": True,
                "sponsorship_status": "unknown",
                "sponsor_company_metadata": {"company_name": "Marshmallow Ltd"},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": True,
            "use_sponsor_lookup": True,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertEqual(1, len(bodies))
        self.assertIn("Marshmallow [Sponsor-licensed]", bodies[0])
        self.assertIn("Fit: SWE 54% | AI/ML 30%", bodies[0])
        self.assertNotIn("Sponsorship:", bodies[0])

    def test_sponsorship_line_only_shows_for_non_unknown_status(self):
        jobs = [
            {
                "company": "Palantir",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "SWE",
                "ranking_score": 0.54,
                "top_score": 0.54,
                "second_profile": "AI/ML",
                "second_score": 0.30,
                "score_margin": 0.10,
                "is_sponsor_licensed_employer": True,
                "sponsorship_status": "explicit_no",
                "sponsor_company_metadata": {},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": True,
            "use_sponsor_lookup": True,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertIn("Palantir [Sponsor-licensed]", bodies[0])
        self.assertIn("Fit: SWE 54% | AI/ML 30%", bodies[0])
        self.assertIn("Sponsorship: explicit no", bodies[0])

    def test_lookup_marker_can_show_without_textual_sponsorship_line(self):
        jobs = [
            {
                "company": "PhysicsX",
                "title": "Machine Learning Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "AI/ML",
                "ranking_score": 0.54,
                "top_score": 0.54,
                "second_profile": "SWE",
                "second_score": 0.30,
                "score_margin": 0.10,
                "is_sponsor_licensed_employer": True,
                "sponsorship_status": "explicit_no",
                "sponsor_company_metadata": {"company_name": "PhysicsX"},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": False,
            "use_sponsor_lookup": True,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertIn("PhysicsX [Sponsor-licensed]", bodies[0])
        self.assertIn("Fit: AI/ML 54% | SWE 30%", bodies[0])
        self.assertNotIn("Sponsorship:", bodies[0])

    def test_fit_line_falls_back_to_existing_fit_summary_when_structured_scores_are_missing(self):
        jobs = [
            {
                "company": "Example",
                "title": "Data Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "fit_summary": "Data Analyst 58% | SWE 51%",
                "ranking_score": 0.58,
                "score_margin": 0.07,
                "is_sponsor_licensed_employer": False,
                "sponsorship_status": "unknown",
                "sponsor_company_metadata": {},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertIn("Fit: Data Analyst 58% | SWE 51%", bodies[0])

    def test_why_apply_line_is_rendered_when_present(self):
        jobs = [
            {
                "company": "Example",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "SWE",
                "ranking_score": 0.84,
                "top_score": 0.58,
                "second_profile": "Data Analyst",
                "second_score": 0.46,
                "score_margin": 0.12,
                "why_apply": (
                    "Junior-friendly team with clear backend work. "
                    "Your Python experience transfers well."
                ),
                "is_sponsor_licensed_employer": False,
                "sponsorship_status": "unknown",
                "sponsor_company_metadata": {},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertIn(
            (
                "Why apply: Junior-friendly team with clear backend work. "
                "Your Python experience transfers well."
            ),
            bodies[0],
        )

    def test_html_digest_renders_button_and_hides_raw_url_text(self):
        jobs = [
            {
                "company": "Example",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "SWE",
                "ranking_score": 0.84,
                "top_score": 0.58,
                "second_profile": "Data Analyst",
                "second_score": 0.46,
                "score_margin": 0.12,
                "why_apply": "Strong junior engineering fit.",
                "is_sponsor_licensed_employer": False,
                "sponsorship_status": "unknown",
                "sponsor_company_metadata": {},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        bodies = build_digest_html_bodies(jobs, recipient_profile)

        self.assertEqual(1, len(bodies))
        self.assertIn(">Open Role</a>", bodies[0])
        self.assertIn('href="https://example.com/job"', bodies[0])
        self.assertNotIn(">https://example.com/job<", bodies[0])
        self.assertIn("New roles worth a look", bodies[0])
        self.assertIn("Strong junior engineering fit.", bodies[0])
        self.assertIn("Strong Match", bodies[0])
        self.assertIn("max-width:920px", bodies[0])
        self.assertIn("padding:12px 6px", bodies[0])

    def test_html_digest_includes_sponsorship_summary_when_enabled(self):
        jobs = [
            {
                "company": "Palantir",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "top_profile": "SWE",
                "ranking_score": 0.54,
                "top_score": 0.54,
                "second_profile": "AI/ML",
                "second_score": 0.30,
                "score_margin": 0.10,
                "is_sponsor_licensed_employer": True,
                "sponsorship_status": "explicit_no",
                "sponsor_company_metadata": {},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": True,
            "use_sponsor_lookup": True,
        }

        bodies = build_digest_html_bodies(jobs, recipient_profile)

        self.assertIn("Palantir [Sponsor-licensed]", bodies[0])
        self.assertIn("Sponsorship: explicit no", bodies[0])


if __name__ == "__main__":
    unittest.main()
