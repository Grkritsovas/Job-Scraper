import json
import os
import unittest
from unittest.mock import patch

from config.recipient_profiles import load_recipient_profiles


class RecipientProfilesTests(unittest.TestCase):
    def test_loads_profiles_from_env_json(self):
        configured = [
            {
                "id": "george",
                "email": "george@example.com",
                "semantic_profiles": ["swe", "data_science"],
                "min_top_score": 0.51,
                "negative_profile_texts": ["senior role"],
                "seniority_penalty_weight": 0.25,
                "preferred_salary_max_gbp": 45000,
                "salary_hard_cap_gbp": 50000,
                "salary_penalty_max": 0.35,
                "care_about_sponsorship": True,
                "use_sponsor_lookup": True,
            }
        ]

        with patch.dict(
            os.environ,
            {"RECIPIENT_PROFILES_JSON": json.dumps(configured)},
            clear=True,
        ):
            profiles = load_recipient_profiles()

        self.assertEqual(1, len(profiles))
        self.assertEqual("george", profiles[0]["id"])
        self.assertEqual("george@example.com", profiles[0]["email"])
        self.assertEqual(["swe", "data_science"], profiles[0]["semantic_profiles"])
        self.assertEqual(0.51, profiles[0]["min_top_score"])
        self.assertEqual(["senior role"], profiles[0]["negative_profile_texts"])
        self.assertEqual(0.25, profiles[0]["seniority_penalty_weight"])
        self.assertEqual(45000.0, profiles[0]["preferred_salary_max_gbp"])
        self.assertEqual(50000.0, profiles[0]["salary_hard_cap_gbp"])
        self.assertEqual(0.35, profiles[0]["salary_penalty_max"])
        self.assertTrue(profiles[0]["care_about_sponsorship"])
        self.assertTrue(profiles[0]["use_sponsor_lookup"])

    def test_falls_back_to_single_recipient_from_sender_email(self):
        with patch.dict(
            os.environ,
            {"JOB_SCRAPER_EMAIL": "sender@example.com"},
            clear=True,
        ):
            profiles = load_recipient_profiles()

        self.assertEqual(1, len(profiles))
        self.assertEqual("default", profiles[0]["id"])
        self.assertEqual("sender@example.com", profiles[0]["email"])
        self.assertEqual(
            ["swe", "data_science", "ai_ml_engineer"],
            profiles[0]["semantic_profiles"],
        )


if __name__ == "__main__":
    unittest.main()
