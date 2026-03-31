import json
import os
import unittest
from unittest.mock import patch

from config.target_config import load_configured_target_details


class TargetConfigTests(unittest.TestCase):
    def test_example_files_are_used_when_no_overrides_exist(self):
        with patch.dict(os.environ, {}, clear=True):
            details = load_configured_target_details()

        self.assertIn(details["ashby"]["source"], {"local_file", "example_file"})
        self.assertTrue(details["ashby"]["values"])

    def test_environment_variables_override_example_files(self):
        with patch.dict(
            os.environ,
            {"ASHBY_COMPANIES_JSON": json.dumps(["custom-ashby-target"])},
            clear=True,
        ):
            details = load_configured_target_details()

        self.assertEqual("environment", details["ashby"]["source"])
        self.assertEqual(["custom-ashby-target"], details["ashby"]["values"])


if __name__ == "__main__":
    unittest.main()
