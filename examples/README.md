# Examples

These files are the quickest way to understand the expected config shapes.

They are kept as valid runtime inputs, so the JSON files intentionally do not contain inline comments.

## Files

- `recipient_profiles.example.json`
  Complete multi-recipient example for `RECIPIENT_PROFILES_JSON` or `recipient_profiles.local.json`.
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

## Recipient Profile Notes

Minimum useful fields:
- `id`
- `email`

Common ranking and formatting fields:
- `semantic_profiles`
- `semantic_profile_texts`
- `min_top_score`
- `negative_profile_texts`
- `cv_summary`
- `seniority_penalty_weight`
- `preferred_salary_max_gbp`
- `salary_hard_cap_gbp`
- `salary_penalty_max`
- `care_about_sponsorship`
- `care_about_hard_eligibility`
- `use_sponsor_lookup`

Practical notes:
- The hard filters are intentionally junior-oriented.
- `semantic_profile_texts` is where the best personalization happens.
- If you use a custom semantic profile id and omit custom text, the app can fall back to generated profile text, but explicit text usually ranks better.
- `cv_summary` and `care_about_hard_eligibility` only affect the optional Gemini reranker.

## Target File Notes

- Ashby and Lever targets can be plain slugs or full public board URLs.
- Full URLs are useful for filtered boards such as Ashby `locationId=...` or EU Lever boards on `jobs.eu.lever.co`.
- Target precedence is:
  1. environment variable
  2. local file
  3. bundled example file
