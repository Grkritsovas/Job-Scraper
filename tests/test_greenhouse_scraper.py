import unittest

from greenhouse_scraper import normalize_board_token


class GreenhouseScraperTests(unittest.TestCase):
    def test_normalize_board_token_from_embed_url_query(self):
        self.assertEqual(
            "Stripe",
            normalize_board_token(
                "https://boards.greenhouse.io/embed/job_board?for=Stripe&offices%5B%5D=87009"
            ),
        )

    def test_normalize_board_token_from_board_url(self):
        self.assertEqual(
            "dept",
            normalize_board_token("https://job-boards.greenhouse.io/dept?keyword=London"),
        )


if __name__ == "__main__":
    unittest.main()
