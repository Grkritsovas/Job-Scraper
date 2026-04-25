# Configuration Guide

This project now loads recipient profiles from the database only. Runtime recipient config lives in `app_config.recipient_profiles.config_json`.

## Required Hosted Setup

Required GitHub Actions secrets:
- `JOB_SCRAPER_EMAIL`
- `JOB_SCRAPER_APP_PASSWORD`
- `DATABASE_URL`

Optional GitHub Actions secret:
- `GEMINI_API_KEY`

Optional GitHub Actions variables:
- `JOB_SCRAPER_LLM_MODEL`
- `JOB_SCRAPER_LLM_TOP_N`
- `JOB_SCRAPER_LLM_BATCH_SIZE`
- `JOB_SCRAPER_LLM_DESCRIPTION_CHARS`
- `JOB_SCRAPER_LLM_RETRY_ATTEMPTS`
- `JOB_SCRAPER_LLM_RETRY_BASE_SECONDS`
- `JOB_SCRAPER_MAX_SEMANTIC_EMAIL_JOBS`
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`
- `SPONSOR_COMPANIES_CSV`
- `SPONSOR_COMPANIES_CSV_TEXT`

## Runtime Recipient Profiles

The scraper reads enabled profiles from:
- `app_config.recipient_profiles`

Schema columns:
- `recipient_id`
- `email`
- `enabled`
- `config_json`
- `created_at`
- `updated_at`

Version history lives in:
- `app_config.recipient_profile_versions`

The app uses a direct Postgres connection through `DATABASE_URL`. It does not read recipient profiles from GitHub secrets or local runtime JSON files.

## Grouped Recipient Profile Shape

Each `config_json` record should look like this:

```json
{
  "id": "george",
  "enabled": true,
  "delivery": {
    "email": "george@example.com"
  },
  "candidate": {
    "summary": "Short factual candidate summary.",
    "education_status": "Graduated Oct 2025; not a current student.",
    "target_roles": [
      {"id": "swe"},
      {"id": "data_science", "match_text": "Custom profile text"}
    ]
  },
  "job_preferences": {
    "target_seniority": {
      "max_explicit_years": 1,
      "boost_multiplier": 1.2,
      "boost_title_terms": ["junior", "grad", "graduate", "entry level", "entry-level"]
    },
    "salary": {
      "preferred_max_gbp": 45000,
      "hard_cap_gbp": 70000,
      "penalty_strength": 0.35
    }
  },
  "eligibility": {
    "needs_sponsorship": false,
    "work_authorization_summary": "Compact UK work authorization context for Gemini.",
    "check_hard_eligibility": false,
    "use_sponsor_lookup": false
  },
  "matching": {
    "semantic_threshold": 0.42
  },
  "llm_review": {
    "extra_screening_guidance": [],
    "extra_final_ranking_guidance": []
  }
}
```

## What Each Field Affects

- `candidate.target_roles`
  Defines the role families used for semantic matching.
- `candidate.target_roles[*].match_text`
  Overrides the built-in semantic profile text for that role.
- `candidate.summary`
  Gives Gemini compact candidate context.
- `candidate.education_status`
  Gives Gemini explicit graduate/student status. This is used for internships, placements, and student-programme judgment.
- `job_preferences.target_seniority.max_explicit_years`
  Controls the regex-based experience filter.
- `job_preferences.target_seniority.boost_multiplier`
  Multiplies semantic scores for titles that match the configured boost terms.
- `job_preferences.target_seniority.boost_title_terms`
  Terms that trigger the junior-title boost.
- `job_preferences.salary.preferred_max_gbp`
  Soft salary preference ceiling.
- `job_preferences.salary.hard_cap_gbp`
  Salary value where the maximum salary penalty is reached.
- `job_preferences.salary.penalty_strength`
  Maximum salary penalty subtracted from ranking score.
- `eligibility.needs_sponsorship`
  Enables sponsorship-aware output and interpretation.
- `eligibility.work_authorization_summary`
  Gives Gemini compact UK work authorization context, such as visa status, settled/pre-settled status, citizenship, or residency facts.
- `eligibility.check_hard_eligibility`
  Adds stricter Gemini judgment for SC/DV clearance, nationality restrictions, and explicit UK residency requirements.
- `eligibility.use_sponsor_lookup`
  Adds sponsor-license lookup markers based on the sponsor-company CSV.
- `matching.semantic_threshold`
  Minimum ranking score required after semantic scoring, title boost, and salary penalty.
- `llm_review.extra_screening_guidance`
  Extra natural-language rules injected into Gemini pass one.
- `llm_review.extra_final_ranking_guidance`
  Extra natural-language rules injected into Gemini pass two.

## Matching Flow

1. Scrape jobs from the configured sources.
2. Drop jobs already seen for that recipient.
3. Apply hard filters:
   - title seniority/commercial/eligibility terms, with recipient-aware exceptions for explicitly targeted role families such as marketing
   - location
   - authorization/eligibility mismatch
   - explicit experience requirement above `max_explicit_years`
4. Score remaining jobs against semantic target-role profiles.
5. Apply the configured junior-title boost when the title matches one of the boost terms.
6. Apply the optional salary penalty.
7. Drop jobs below `matching.semantic_threshold`.
8. If Gemini is enabled, run two-pass Gemini screening and reranking.

Recipient diagnostic lines include the review mode and counts. When Gemini fails,
the line also includes `review_error_stage` and a compact `review_error` value so
workflow logs show whether the failure happened during client setup, batch
screening, or final reranking.

The run also prints a final `[run_summary]` line with candidate counts, recipient
outcomes, jobs sent, reviewed jobs, source failures, and Gemini failure stages.
If one source family fails, the run continues with jobs from the successful
source families and records a `[scrape_failure:<source>]` diagnostic line. If
all source families fail, the run stops instead of sending an empty-looking
result.

## Replay Debugging

Save a replay snapshot during a normal run with:

```powershell
python run_all.py --save-run runs/latest.json
```

The snapshot includes scraped jobs, enriched jobs, runtime recipient profiles,
recipient outcomes, and diagnostics. Treat it as local debugging data because it
can include job descriptions and candidate summaries. The default `runs/`
directory is ignored by Git.

Replay ranking and review without scraping, sending email, or marking jobs seen:

```powershell
python tools/replay_run.py runs/latest.json --recipient george
```

By default replay uses recipient profiles saved in the snapshot. To tune the
current database profile against the same saved job set, use:

```powershell
python tools/replay_run.py runs/latest.json --profiles current-db --recipient george
```

Use `--semantic-only` to temporarily disable Gemini for the replay process, and
`--preview-dir runs/previews` to write local digest HTML/text previews.

## Concurrency

- Recipient processing runs concurrently with a built-in cap of `4`.
- Recipient concurrency is also clamped by the number of enabled profiles, so smaller runs only use the threads they need.
- The implementation enforces a hard upper bound of `8` recipient workers even if the code cap is raised later.
- Gemini calls inside the recipient threads are capped separately at `4` concurrent requests.
- Gemini retrying uses exponential backoff with a shared retry budget of up to `10` minutes per recipient rerank attempt.
- Scraping runs the four source families in parallel:
  - Ashby
  - Greenhouse
  - Lever
  - Next.js
- Each source family still runs serially inside its own scraper.
- Per-job description fetching is unchanged and is not parallelized separately.

This project is intended for a small admin-run setup, roughly up to `8` recipients per run.

## Target Configuration

Supported target config variables:
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

Target precedence:
1. GitHub Actions variable or environment variable
2. local file such as `ashby_companies.local.json`
3. bundled example file in `examples/`

## Sponsorship Lookup

Supported inputs:
- `SPONSOR_COMPANIES_CSV_TEXT`
- `SPONSOR_COMPANIES_CSV`
- `sponsor_companies.local.csv`
- `data/uk_sponsors_companies.csv`

The CSV only needs a `company_name` column.

If `use_sponsor_lookup` is enabled for a recipient, the app adds a `[Sponsor-licensed]` marker when the company matches the CSV.

## Loading Profiles Into The Database

Create or update grouped recipient profiles directly in:
- `app_config.recipient_profiles`

Recommended workflow:
1. Build the grouped JSON shape shown above.
2. Insert or update each profile in Supabase SQL editor or another Postgres client.
3. Verify enabled rows with:

```sql
select recipient_id, email, enabled
from app_config.recipient_profiles
order by recipient_id;
```

Validate stored profiles before a run with:

```powershell
python tools/validate_recipient_profiles.py
```

Use `--enabled-only` to check only enabled profiles. The validator loads profile
JSON from the configured database and runs the same normalization path used by
the scraper.
