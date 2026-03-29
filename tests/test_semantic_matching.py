import unittest

from semantic_matching import rank_jobs


class FakeMatcher:
    def score_description(self, description, profile_specs):
        top_label = profile_specs[0]["label"]
        second_label = profile_specs[1]["label"] if len(profile_specs) > 1 else top_label
        top_score = {
            "strong_fit": 0.56,
            "borderline_fit": 0.46,
        }.get(description, 0.52)
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
    def test_recipient_with_sponsorship_concern_rejects_explicit_no(self):
        jobs = [
            make_job(
                url="https://example.com/no",
                sponsorship_status="explicit_no",
            )
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "care_about_sponsorship": True,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual([], ranked_jobs)

    def test_recipient_without_sponsorship_concern_keeps_explicit_no(self):
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

    def test_sponsor_lookup_boost_changes_ranking_order(self):
        jobs = [
            make_job(
                url="https://example.com/unknown",
                title="Backend Software Engineer",
                sponsorship_status="unknown",
                is_sponsor_licensed_employer=False,
            ),
            make_job(
                url="https://example.com/licensed",
                title="Backend Platform Engineer",
                sponsorship_status="unknown",
                is_sponsor_licensed_employer=True,
            ),
        ]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.45,
            "care_about_sponsorship": True,
            "use_sponsor_lookup": True,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual("https://example.com/licensed", ranked_jobs[0]["url"])

    def test_recipient_specific_threshold_applies(self):
        jobs = [make_job(url="https://example.com/borderline", description="borderline_fit")]
        recipient_profile = {
            "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
            "min_top_score": 0.47,
            "care_about_sponsorship": False,
            "use_sponsor_lookup": False,
        }

        ranked_jobs = rank_jobs(jobs, recipient_profile, matcher=FakeMatcher())
        self.assertEqual([], ranked_jobs)


if __name__ == "__main__":
    unittest.main()
