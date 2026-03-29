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
                "sponsor_company_metadata": {"sub_tier": "Skilled Worker", "town": "London"},
            }
        ]
        recipient_profile = {
            "care_about_sponsorship": True,
            "use_sponsor_lookup": True,
        }

        bodies = build_digest_bodies(jobs, recipient_profile)

        self.assertEqual(1, len(bodies))
        self.assertIn("Marshmallow [Sponsor-licensed]", bodies[0])
        self.assertIn(
            "Sponsorship: unknown, sponsor-licensed employer (Skilled Worker, London)",
            bodies[0],
        )


if __name__ == "__main__":
    unittest.main()
