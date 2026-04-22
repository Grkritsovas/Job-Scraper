# Examples

These files show the grouped recipient-profile shape that gets stored in the database and the starter target lists used by the scrapers.

## Files

- `recipient_profiles.example.json`
  Grouped recipient-profile example. This is the shape stored in `app_config.recipient_profiles.config_json`.
- `sponsor_companies.example.csv`
  Minimal sponsor-company lookup CSV. The app only requires a `company_name` column.
- `ashby_companies.uk.example.json`
  UK-focused Ashby starter targets.
- `greenhouse_boards.uk.example.json`
  UK-focused Greenhouse starter targets.
- `lever_companies.uk.example.json`
  UK-focused Lever starter targets.
- `nextjs_urls.example.json`
  Site-specific Next.js URLs for boards that expose `__NEXT_DATA__`.

## Recipient Profile Shape

Top-level fields:
- `id`
- `enabled`
- `delivery.email`
- `candidate.summary`
- `candidate.target_roles`
- `job_preferences.target_seniority`
- `job_preferences.salary`
- `eligibility`
- `matching.semantic_threshold`
- `llm_review`

Useful notes:
- `candidate.target_roles[*].match_text` is the strongest personalization lever for semantic ranking.
- `job_preferences.target_seniority.max_explicit_years` controls the regex-based experience filter.
- `job_preferences.target_seniority.boost_multiplier` and `boost_title_terms` control the title boost for junior-oriented titles.
- `llm_review.extra_screening_guidance` affects Gemini pass one.
- `llm_review.extra_final_ranking_guidance` affects Gemini pass two.

## Target File Notes

- Ashby and Lever targets can be plain slugs or full public board URLs.
- Full URLs are useful for filtered boards such as Ashby `locationId=...` or EU Lever boards on `jobs.eu.lever.co`.
- Target precedence is:
  1. environment variable
  2. local file
  3. bundled example file
