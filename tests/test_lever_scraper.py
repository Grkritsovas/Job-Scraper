import unittest

from lever_scraper import get_job_locations, get_primary_location, is_flexible_location
from utils import is_uk_location


class LeverScraperTests(unittest.TestCase):
    def test_primary_location_is_used_for_non_flexible_roles(self):
        job = {
            "categories": {
                "location": "New York, NY",
                "allLocations": ["New York, NY", "London, United Kingdom"],
            }
        }

        primary_location = get_primary_location(job)
        locations = get_job_locations(job)

        self.assertEqual("New York, NY", primary_location)
        self.assertFalse(is_flexible_location(primary_location))
        self.assertFalse(is_uk_location([primary_location]))
        self.assertTrue(is_uk_location(locations))

    def test_remote_primary_location_can_fall_back_to_all_locations(self):
        job = {
            "categories": {
                "location": "Remote",
                "allLocations": ["United Kingdom"],
            }
        }

        primary_location = get_primary_location(job)
        locations = get_job_locations(job)

        self.assertTrue(is_flexible_location(primary_location))
        self.assertTrue(is_uk_location(locations))


if __name__ == "__main__":
    unittest.main()
