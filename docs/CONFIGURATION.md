# Configuration Guide

This document explains where the controls live, how to set them, and what each one affects downstream.

## Configuration Surfaces

There are five main places to configure the app:

1. GitHub Actions secrets
   Sensitive values such as credentials, database URLs, and full recipient JSON.
2. GitHub Actions variables
   Non-secret controls such as LLM model choice, top-N limits, and target overrides.
3. `RECIPIENT_PROFILES_JSON`
   The main per-recipient control surface. This is where profile behavior should usually live.
4. Local fallback files
   Useful for testing locally without GitHub Actions.
5. Bundled example files in `examples/`
   UK-focused starter targets and example config shapes.

## Recommended Hosted Setup

1. Fork the repo.
2. Create a Postgres database.
3. Add these required GitHub Actions secrets:
   - `JOB_SCRAPER_EMAIL`
   - `JOB_SCRAPER_APP_PASSWORD`
   - `DATABASE_URL`
   - `RECIPIENT_PROFILES_JSON`
4. Optionally add `GEMINI_API_KEY` if you want Gemini reranking.
5. Optionally add non-secret GitHub Actions variables for tuning.
6. Run the workflow manually once.
7. Enable the schedule.

## GitHub Secrets

### Required

- `JOB_SCRAPER_EMAIL`
  Sender address for digest emails.
- `JOB_SCRAPER_APP_PASSWORD`
  App password for the sender account.
- `DATABASE_URL`
  Postgres connection string for persistent seen-job tracking.
- `RECIPIENT_PROFILES_JSON`
  The full recipient configuration array.

### Optional

- `GEMINI_API_KEY`
  Enables semantic retrieval plus Gemini reranking.
- `SPONSOR_COMPANIES_CSV_TEXT`
  Inline sponsor-company CSV content if you do not want a file path.

## GitHub Variables

### Optional Gemini Controls

- `JOB_SCRAPER_LLM_MODEL`
  Model id for Gemini reranking.
  Recommended start: `gemini-2.5-flash`
- `JOB_SCRAPER_LLM_TOP_N`
  How many unseen semantic matches go to Gemini.
  Recommended start: `20` to `40`
- `JOB_SCRAPER_LLM_BATCH_SIZE`
  Batch size for first-pass Gemini screening.
  Recommended start: `10`
- `JOB_SCRAPER_LLM_DESCRIPTION_CHARS`
  Description excerpt length sent to Gemini.
  Recommended start: `1600`
- `JOB_SCRAPER_LLM_RETRY_ATTEMPTS`
  Total Gemini call attempts for retryable errors such as `429` and `503`.
  Default: `3`
- `JOB_SCRAPER_LLM_RETRY_BASE_SECONDS`
  Base backoff in seconds between Gemini retries.
  Default: `2.0`
- `JOB_SCRAPER_MAX_SEMANTIC_EMAIL_JOBS`
  Digest cap when Gemini is not enabled.
  Default: `60`

### Optional Target Overrides

- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

If these are not set, the app falls back to:
1. local files such as `ashby_companies.local.json`
2. bundled example files in `examples/`

### Optional Sponsorship Inputs

- `SPONSOR_COMPANIES_CSV`
  File path to a sponsor-company CSV

## Matching Modes

### Semantic-Only Mode

Used when `GEMINI_API_KEY` is not set.

Behavior:
- jobs are ranked with the selected sentence-transformer
- the digest is capped by `JOB_SCRAPER_MAX_SEMANTIC_EMAIL_JOBS`
- no Gemini cost

### Semantic + Gemini Rerank Mode

Used when `GEMINI_API_KEY` is set.

Behavior:
- semantic ranking is used for retrieval
- the top unseen jobs go through Gemini
- only the final Gemini shortlist is emailed
- all Gemini-reviewed jobs are stored as seen
- if Gemini fails after retries, the app sends nothing for that run

Cost note:
- the first Gemini-enabled run can cost more because many jobs may be unseen at once
- later runs are usually cheaper because reviewed jobs are stored as seen

## Recipient Profiles

Primary source:
- `RECIPIENT_PROFILES_JSON`

Local fallback:
- `recipient_profiles.local.json`

Example:
- [examples/recipient_profiles.example.json](../examples/recipient_profiles.example.json)

### Minimum Useful Fields

- `id`
- `email`

### Common Fields and What They Affect

- `semantic_profiles`
  Which role families the recipient targets.
- `semantic_profile_texts`
  Custom text for each target profile. This is one of the strongest levers for better matching.
- `min_top_score`
  Minimum semantic score needed to survive ranking.
- `negative_profile_texts`
  Text used to apply a soft penalty to roles that sound too senior, too independent, or otherwise off-target.
- `cv_summary`
  Short supporting context for Gemini. Keep it compact and factual.
- `seniority_penalty_weight`
  How strongly the negative-profile similarity reduces ranking score.
- `junior_boost_multiplier`
  Score multiplier applied when the title contains a configured junior-oriented term.
- `junior_boost_terms`
  Terms that trigger the junior title boost.
- `preferred_salary_max_gbp`
  Preferred salary ceiling for soft salary penalties.
- `salary_hard_cap_gbp`
  Upper salary bound after which the maximum salary penalty applies.
- `salary_penalty_max`
  Maximum amount the salary penalty can subtract from ranking score.
- `care_about_sponsorship`
  Adds sponsorship-related information to the digest when the job text provides it.
- `care_about_hard_eligibility`
  Adds stricter Gemini instructions around SC/DV clearance, nationality restrictions, and explicit UK residency requirements.
- `use_sponsor_lookup`
  Adds `[Sponsor-licensed]` markers based on the sponsor-company CSV lookup.

### Important Distinctions

- `care_about_sponsorship` is about sponsorship-related output and interpretation.
- `care_about_hard_eligibility` is about stricter Gemini judgment for hard eligibility constraints.
- `cv_summary` and `care_about_hard_eligibility` affect the Gemini reranker only.

## Targets

Supported target config variables:
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

Target precedence:
1. GitHub Actions variable or environment variable
2. local file such as `ashby_companies.local.json`
3. bundled example file in `examples/`

Notes:
- Ashby and Lever targets can be plain slugs or full public URLs.
- Full URLs are useful for location-filtered boards.
- The bundled example files are UK-focused starter lists.

## Sponsorship Lookup

Sponsorship lookup adds metadata only. It is not a live sponsorship check.

Supported inputs:
- `SPONSOR_COMPANIES_CSV_TEXT`
- `SPONSOR_COMPANIES_CSV`
- `sponsor_companies.local.csv`
- `data/uk_sponsors_companies.csv`

The CSV only needs a `company_name` column.

If enabled for a recipient:
- `use_sponsor_lookup` adds a `[Sponsor-licensed]` marker when the company matches the CSV
- `care_about_sponsorship` adds a `Sponsorship: ...` line when the job text says something useful

## Local Configuration

Useful local files:
- `recipient_profiles.local.json`
- `ashby_companies.local.json`
- `greenhouse_boards.local.json`
- `lever_companies.local.json`
- `nextjs_urls.local.json`
- `sponsor_companies.local.csv`

Local defaults:
- SQLite database in `job_scraper.db`
- example target files if local overrides are absent

## Practical Starting Point

If you want a simple hosted setup:

- set the four required secrets
- start with the bundled example target lists
- keep Gemini off for the first sanity check
- then add `GEMINI_API_KEY`
- start Gemini with:
  - `JOB_SCRAPER_LLM_MODEL = gemini-2.5-flash`
  - `JOB_SCRAPER_LLM_TOP_N = 20`
  - `JOB_SCRAPER_LLM_BATCH_SIZE = 10`
  - `JOB_SCRAPER_LLM_DESCRIPTION_CHARS = 1600`

That gives you a conservative baseline before tuning further.
