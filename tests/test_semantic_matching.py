import unittest

from semantic_matching import build_profile_specs, get_hard_filter_reason, rank_jobs


class FakeMatcher:
    def __init__(self):
        self.scored_descriptions = []

    def score_description(self, description, profile_specs, negative_profile_texts=None):
        self.scored_descriptions.append(description)
        top_label = profile_specs[0]["label"]
        second_label = profile_specs[1]["label"] if len(profile_specs) > 1 else top_label
        if "strong_fit" in description:
            top_score = 0.56
        elif "borderline_fit" in description:
            top_score = 0.46
        else:
            top_score = 0.52
        second_score = max(0.0, top_score - 0.08)
        return {
            "profile_scores": {
                spec["label"]: top_score - (index * 0.08)
                for index, spec in enumerate(profile_specs)
            },
            "top_profile": top_label,
            "top_score": top_score,
            "ranking_score": top_score,
            "second_profile": second_label,
            "second_score": second_score,
            "score_margin": top_score - second_score,
            "seniority_penalty_score": 0.0,
            "seniority_penalty_applied": 0.0,
            "fit_summary": " | ".join(
                f"{spec['label']} {round((top_score - (index * 0.08)) * 100)}%"
                for index, spec in enumerate(profile_specs)
            ),
        }


def make_job(**overrides):
    base = {
        "company": "Example",
        "title": "Software Engineer",
        "url": "https://example.com/job",
        "description": "strong_fit",
        "locations": ["London"],
        "location": "London",
        "source": "example",
        "target_value": "example",
        "sponsorship_status": "unknown",
        "is_sponsor_licensed_employer": False,
    }
    base.update(overrides)
    return base


class SemanticMatchingTests(unittest.TestCase):
    def test_unknown_profile_id_falls_back_to_generated_profile_text(self):
        recipient_profile = {
            "semantic_profiles": ["marketing_assistant"],
            "semantic_profile_texts": {},
        }

        specs = build_profile_specs(recipient_profile)

        self.assertEqual(1, len(specs))
        self.assertEqual("marketing_assistant", specs[0]["id"])
        self.assertEqual("Marketing Assistant", specs[0]["label"])
        self.assertIn("entry-level marketing assistant roles", specs[0]["text"])

    def test_get_hard_filter_reason_identifies_commercial_title(self):
        reason = get_hard_filter_reason(
            make_job(title="Account Executive", description="strong_fit")
        )
        self.assertEqual("title_commercial", reason)

    def test_get_hard_filter_reason_rejects_two_plus_years_for_junior_pipeline(self):
        reason = get_hard_filter_reason(
            make_job(description="Requires 2+ years of experience in Python."),
        )
        self.assertEqual("experience", reason)

    def test_sponsorship_status_is_info_only_for_ranking(self):
        jobs = [
            make_job(
                url="https://example.com/no",
                sponsorship_status="explicit_no",
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual(1, len(ranked_jobs))

    def test_recipient_specific_threshold_applies(self):
        jobs = [make_job(url="https://example.com/borderline", description="borderline_fit")]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.47,
            "negative_profile_texts": [],
            "seniority_penalty_weight": 0.18,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual([], ranked_jobs)

    def test_recipient_can_disable_seniority_penalty(self):
        jobs = [make_job(url="https://example.com/soft-penalty")]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "negative_profile_texts": ["senior role"],
            "seniority_penalty_weight": 0.0,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual(1, len(ranked_jobs))

    def test_salary_penalty_filters_unrealistic_salary_range(self):
        jobs = [
            make_job(
                url="https://example.com/high-salary",
                description="Salary range: GBP 51,000 - GBP 80,000 plus benefits.",
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "preferred_salary_max_gbp": 45000,
            "salary_hard_cap_gbp": 50000,
            "salary_penalty_max": 0.35,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual([], ranked_jobs)

    def test_salary_penalty_does_not_apply_when_not_configured(self):
        jobs = [
            make_job(
                url="https://example.com/high-salary-allowed",
                description="Salary range: GBP 51,000 - GBP 80,000 plus benefits.",
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual(1, len(ranked_jobs))

    def test_html_like_description_can_still_rank(self):
        jobs = [
            make_job(
                url="https://example.com/html",
                description="<html><body>role page</body></html>",
                description_looks_like_html=True,
                description_status="raw_html_fallback",
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.43,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual(1, len(ranked_jobs))
        self.assertTrue(ranked_jobs[0]["description_looks_like_html"])

    def test_rank_jobs_includes_title_and_strips_boilerplate_in_match_text(self):
        matcher = FakeMatcher()
        jobs = [
            make_job(
                title="Full Stack Engineer",
                description=(
                    "Build full-stack product features with React and Java. "
                    "Our Commitment to Diversity, Equity, Inclusion and Belonging "
                    "We believe attracting and retaining the best talent matters."
                ),
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.43,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        rank_jobs(jobs, recipient_profile, matcher=matcher)

        self.assertEqual(1, len(matcher.scored_descriptions))
        scored_text = matcher.scored_descriptions[0]
        self.assertIn("Role title: Full Stack Engineer", scored_text)
        self.assertIn("Build full-stack product features with React and Java.", scored_text)
        self.assertNotIn("Our Commitment to Diversity", scored_text)


if __name__ == "__main__":
    unittest.main()
