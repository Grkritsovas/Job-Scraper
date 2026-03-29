import unittest
from pathlib import Path

from sponsorship import (
    classify_sponsorship_status,
    enrich_jobs,
    load_sponsor_company_lookup,
    normalize_company_lookup_name,
)


class SponsorshipTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/.tmp_sponsorship")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for child in self.test_dir.glob("*"):
            child.unlink()
        self.test_dir.rmdir()

    def test_normalize_company_lookup_name(self):
        self.assertEqual(
            "marshmallow",
            normalize_company_lookup_name(" Marshmallow Ltd. "),
        )
        self.assertEqual(
            "funding circle",
            normalize_company_lookup_name("Funding Circle Plc"),
        )

    def test_load_lookup_and_match_company(self):
        csv_path = self.test_dir / "sponsors.csv"
        csv_path.write_text(
            "Organisation,Town,Industry,Main Tier,Sub Tier,Status\n"
            "Marshmallow Ltd,London,Computer,Worker (A),Skilled Worker,Active\n",
            encoding="utf-8",
        )

        lookup = load_sponsor_company_lookup(csv_path)
        enriched_jobs = enrich_jobs(
            [
                {
                    "company": "Marshmallow",
                    "title": "Software Engineer",
                    "description": "Build backend services.",
                }
            ],
            lookup,
        )

        self.assertIn("marshmallow", lookup)
        self.assertTrue(enriched_jobs[0]["is_sponsor_licensed_employer"])
        self.assertEqual("London", enriched_jobs[0]["sponsor_company_metadata"]["town"])
        self.assertEqual(
            "Skilled Worker",
            enriched_jobs[0]["sponsor_company_metadata"]["sub_tier"],
        )

    def test_classify_sponsorship_statuses(self):
        self.assertEqual(
            "explicit_no",
            classify_sponsorship_status(
                "Software Engineer",
                "Candidates must already have the right to work in the UK.",
            ),
        )
        self.assertEqual(
            "explicit_yes",
            classify_sponsorship_status(
                "ML Engineer",
                "Skilled worker visa sponsorship available for this role.",
            ),
        )
        self.assertEqual(
            "implied_no",
            classify_sponsorship_status(
                "Software Engineer",
                "Will you now or in the future require sponsorship to work in the UK?",
            ),
        )


if __name__ == "__main__":
    unittest.main()
