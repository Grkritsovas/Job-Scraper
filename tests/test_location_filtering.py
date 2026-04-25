import unittest

from shared.locations import get_uk_location_decision
from utils import is_uk_location


class LocationFilteringTests(unittest.TestCase):
    def test_accepts_city_only_uk_locations_seen_in_job_boards(self):
        self.assertTrue(is_uk_location(["Bath"]))
        self.assertTrue(is_uk_location(["Aberdeen (GB)"]))
        self.assertTrue(is_uk_location(["Newcastle, UK"]))
        self.assertTrue(is_uk_location(["Stockton-on-Tees"]))
        self.assertTrue(is_uk_location(["West Midlands"]))

    def test_accepts_common_misspelled_uk_locations_seen_in_feed(self):
        self.assertTrue(is_uk_location(["Cardif (GB)"]))
        self.assertTrue(is_uk_location(["Bournemooth (GB)"]))
        self.assertTrue(is_uk_location(["Middlesborough"]))
        self.assertTrue(is_uk_location(["Shefield"]))

    def test_still_rejects_non_uk_locations(self):
        self.assertFalse(is_uk_location(["Berlin"]))
        self.assertFalse(is_uk_location(["Sydney, Australia"]))
        self.assertFalse(is_uk_location(["Remote (United States)"]))
        self.assertFalse(is_uk_location(["New York, NY"]))
        self.assertFalse(is_uk_location(["Newport Beach, CA"]))

    def test_location_decision_explains_match_or_rejection(self):
        accepted = get_uk_location_decision(["Newcastle, UK"])
        rejected = get_uk_location_decision(["Newport Beach, CA"])

        self.assertTrue(accepted["accepted"])
        self.assertEqual("country_level_uk", accepted["reason"])
        self.assertFalse(rejected["accepted"])
        self.assertEqual("foreign_region", rejected["reason"])
        self.assertEqual("us_state_code", rejected["matched_term"])


if __name__ == "__main__":
    unittest.main()
