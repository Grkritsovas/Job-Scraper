import unittest

from utils import build_digest_bodies


class DigestFormattingTests(unittest.TestCase):
    def test_company_heading_shows_sponsor_marker_for_opted_in_recipient(self):
        jobs = [
            {
                "company": "Marshmallow",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "fit_summary": "SWE 54% | AI/ML 30% | Data Science 28%",
                "ranking_score": 0.54,
                "top_score": 0.54,
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
        self.assertNotIn("Sponsorship:", bodies[0])

    def test_sponsorship_line_only_shows_for_non_unknown_status(self):
        jobs = [
            {
                "company": "Palantir",
                "title": "Software Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "fit_summary": "SWE 54% | AI/ML 30% | Data Science 28%",
                "ranking_score": 0.54,
                "top_score": 0.54,
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
        self.assertIn("Sponsorship: explicit no", bodies[0])

    def test_lookup_marker_can_show_without_textual_sponsorship_line(self):
        jobs = [
            {
                "company": "PhysicsX",
                "title": "Machine Learning Engineer",
                "url": "https://example.com/job",
                "location": "London",
                "fit_summary": "AI/ML 54% | SWE 30%",
                "ranking_score": 0.54,
                "top_score": 0.54,
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
        self.assertNotIn("Sponsorship:", bodies[0])


if __name__ == "__main__":
    unittest.main()
