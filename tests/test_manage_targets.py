import unittest

from manage_targets import resolve_selected_sources


class ManageTargetsTests(unittest.TestCase):
    def test_supports_readme_list_command(self):
        self.assertEqual(
            ["ashby"],
            resolve_selected_sources("list", "ashby", {"ashby", "lever"}),
        )

    def test_supports_legacy_short_form(self):
        self.assertEqual(
            ["ashby"],
            resolve_selected_sources(None, "ashby", {"ashby", "lever"}),
        )

    def test_supports_short_source_form(self):
        self.assertEqual(
            ["ashby"],
            resolve_selected_sources("ashby", None, {"ashby", "lever"}),
        )

    def test_defaults_to_all_sources_when_no_filter_is_given(self):
        self.assertEqual(
            ["ashby", "lever"],
            resolve_selected_sources(None, None, {"lever", "ashby"}),
        )

    def test_rejects_invalid_usage(self):
        with self.assertRaises(ValueError):
            resolve_selected_sources("list", "nope", {"ashby", "lever"})

        with self.assertRaises(ValueError):
            resolve_selected_sources("weird", None, {"ashby", "lever"})


if __name__ == "__main__":
    unittest.main()
