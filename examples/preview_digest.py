from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.digest import build_digest_payloads


def sample_jobs():
    return [
        {
            "company": "Marshmallow",
            "title": "Junior Software Engineer",
            "url": "https://example.com/marshmallow-junior-software-engineer",
            "location": "London",
            "top_profile": "SWE",
            "top_score": 0.86,
            "second_profile": "Data Science",
            "second_score": 0.58,
            "ranking_score": 0.91,
            "score_margin": 0.28,
            "why_apply": (
                "Clear junior engineering scope with supportive delivery work. "
                "Your Python and software project background transfer well."
            ),
            "is_sponsor_licensed_employer": True,
            "sponsorship_status": "explicit_yes",
            "sponsor_company_metadata": {"company_name": "Marshmallow Ltd"},
        },
        {
            "company": "Kpler",
            "title": "Data Analyst",
            "url": "https://example.com/kpler-data-analyst",
            "location": "London",
            "top_profile": "Data Analyst",
            "top_score": 0.71,
            "second_profile": "Data Science",
            "second_score": 0.63,
            "ranking_score": 0.74,
            "score_margin": 0.08,
            "why_apply": (
                "Hands-on analytical role with clear reporting and data interpretation work. "
                "It looks aligned with structured problem solving rather than ownership-heavy delivery."
            ),
            "is_sponsor_licensed_employer": False,
            "sponsorship_status": "unknown",
            "sponsor_company_metadata": {},
        },
        {
            "company": "Multiverse",
            "title": "AI Coach",
            "url": "https://example.com/multiverse-ai-coach",
            "location": "London, Remote (UK)",
            "top_profile": "AI/ML",
            "top_score": 0.62,
            "second_profile": "Data Science",
            "second_score": 0.55,
            "ranking_score": 0.67,
            "score_margin": 0.07,
            "why_apply": (
                "AI-adjacent role with practical technical context and training structure. "
                "It could be a reasonable stretch if you want something less delivery-heavy."
            ),
            "is_sponsor_licensed_employer": False,
            "sponsorship_status": "explicit_no",
            "sponsor_company_metadata": {},
        },
        {
            "company": "Thought Machine",
            "title": "Backend Engineer",
            "url": "https://example.com/thought-machine-backend-engineer",
            "location": "London",
            "top_profile": "SWE",
            "top_score": 0.54,
            "second_profile": "AI/ML",
            "second_score": 0.43,
            "ranking_score": 0.56,
            "score_margin": 0.11,
            "why_apply": (
                "This is a weaker but still plausible engineering match. "
                "The role looks more backend-focused and less junior-coded than the top cards."
            ),
            "is_sponsor_licensed_employer": False,
            "sponsorship_status": "unknown",
            "sponsor_company_metadata": {},
        },
    ]


def sample_recipient():
    return {
        "care_about_sponsorship": True,
        "use_sponsor_lookup": True,
    }


def main():
    output_dir = Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads = build_digest_payloads(sample_jobs(), sample_recipient())
    if not payloads:
        raise RuntimeError("Preview payload generation returned no content.")

    html_path = output_dir / "digest_preview.html"
    text_path = output_dir / "digest_preview.txt"

    html_path.write_text(payloads[0]["html"], encoding="utf-8")
    text_path.write_text(payloads[0]["text"], encoding="utf-8")

    print(f"HTML preview written to: {html_path.resolve()}")
    print(f"Text preview written to: {text_path.resolve()}")


if __name__ == "__main__":
    main()
