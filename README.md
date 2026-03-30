# Job Scraper

Scrapes public job boards, semantically ranks roles against configurable profiles, and sends grouped email digests.

Current sources:
- Ashby public job boards
- Greenhouse Job Board API
- Lever Postings API
- Site-specific Next.js `__NEXT_DATA__` pages

## How It Works

- Targets come from environment variables, local JSON files, or bundled example seed files.
- Runtime targets do not come from the database.
- Jobs are scraped once per run, then enriched once with sponsorship metadata.
- Recipient profiles are loaded from config and scored independently.
- Seen-job state is stored in a database per recipient profile.
- Sponsorship lookup is a static CSV-backed metadata match, not a live company check.
- Local runs use SQLite by default in `job_scraper.db`.
- Hosted runs should use Postgres via `DATABASE_URL`.

## Local Vs Hosted

Local run:
- you run `python run_all.py` on your machine
- targets come from environment variables, local JSON files, or bundled example files
- seen-job state is stored in local SQLite unless you explicitly set `DATABASE_URL`

Hosted run:
- GitHub Actions runs `python run_all.py` in a fresh runner
- targets still come from GitHub Actions variables or the committed example files
- seen-job state must live in Postgres via `DATABASE_URL`, because the runner filesystem is temporary

Practical rule:
- config lives in repo files or GitHub Actions variables
- seen-job history lives in the database

## Architecture

Tiny data flow:
1. Load targets from config.
2. Scrape jobs from Ashby, Greenhouse, Lever, and configured Next.js pages.
3. Normalize URLs, locations, and descriptions.
4. Enrich jobs with sponsorship metadata from the sponsor CSV.
5. Rank jobs separately for each recipient profile.
6. Remove jobs already seen by that recipient.
7. Send the digest email.
8. Store sent job URLs in `recipient_seen_jobs`.

Main modules:
- `run_all.py`: runtime orchestration
- `target_config.py`: target loading and precedence
- `ashby_scraper.py`, `greenhouse_scraper.py`, `lever_scraper.py`, `nextjs_scraper.py`: source-specific scraping
- `descriptions.py`, `locations.py`, `company_names.py`: shared normalization helpers
- `profile_library.py`, `hard_filters.py`, `ranking.py`: matching and ranking pipeline
- `sponsorship.py`: sponsor lookup and text classification
- `storage.py`: recipient seen-job persistence only
- `digest.py`: email digest formatting

## Local Quickstart

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set your Gmail credentials in the shell before running:

```powershell
$env:JOB_SCRAPER_EMAIL = "you@example.com"
$env:JOB_SCRAPER_APP_PASSWORD = "your app password"
```

4. Optional: test without sending email:

```powershell
$env:JOB_SCRAPER_DRY_RUN = "1"
```

5. Optional: create `recipient_profiles.local.json`.
   If you do not, the app falls back to a single recipient using `JOB_SCRAPER_EMAIL`.

6. Optional: create `sponsor_companies.local.csv` if you want sponsorship lookup.

7. Run:

```bash
python run_all.py
```

This creates `job_scraper.db` locally unless you set `DATABASE_URL`.

## Recipient Profiles

Primary config source:
- `RECIPIENT_PROFILES_JSON`

Local fallback:
- `recipient_profiles.local.json`

Bundled example:
- [examples/recipient_profiles.example.json](examples/recipient_profiles.example.json)

One deployment can serve multiple recipients.
Only the person managing the repo / GitHub Actions needs to set up secrets and config.
Additional recipients do not need to fork the repo or do any technical setup; they just need an email address and a profile entry.

Example shape:

```json
[
  {
    "id": "george",
    "email": "you@example.com",
    "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
    "semantic_profile_texts": {},
    "min_top_score": 0.43,
    "negative_profile_texts": [
      "Senior or staff level role requiring multiple years of industry experience, technical leadership, mentoring, architecture ownership, and proven delivery of production systems at scale."
    ],
    "seniority_penalty_weight": 0.18,
    "preferred_salary_max_gbp": 45000,
    "salary_hard_cap_gbp": 70000,
    "salary_penalty_max": 0.35,
    "care_about_sponsorship": false,
    "use_sponsor_lookup": false
  },
  {
    "id": "kamila",
    "email": "other@example.com",
    "semantic_profiles": ["marketing_assistant", "ai_ml"],
    "semantic_profile_texts": {
      "marketing_assistant": "Junior marketing and communications professional with experience supporting marketing teams in structured business environments. Best aligned with early-career marketing assistant, communications support, campaign operations, coordination, and content-support roles.",
      "ai_ml": "Early-career AI and data-focused graduate profile. Best aligned with junior applied AI, machine learning, and analytical support roles where experimentation, modelling fundamentals, and practical Python-based ML work matter more than production ownership."
    },
    "min_top_score": 0.43,
    "negative_profile_texts": [
      "Senior or highly autonomous role requiring proven commercial experience, independent ownership, strategic responsibility, or delivery in real production or business environments. Includes roles expecting multiple years of experience, leadership, mentoring, end-to-end ownership, operational accountability, or advanced specialization."
    ],
    "seniority_penalty_weight": 0.18,
    "preferred_salary_max_gbp": 45000,
    "salary_hard_cap_gbp": 70000,
    "salary_penalty_max": 0.35,
    "care_about_sponsorship": true,
    "use_sponsor_lookup": true
  }
]
```

Minimum useful fields for an extra recipient:
- `id`
- `email`

The other fields are preferences. If two recipients want the same role taste, you can keep the same semantic profiles and thresholds and only change `id` and `email`.
If they do not want the same role taste, give them their own `semantic_profiles` and `semantic_profile_texts`.

Supported recipient fields:
- `id`
- `email`
- `semantic_profiles`
- `semantic_profile_texts`
- `min_top_score`
- `negative_profile_texts`
- `seniority_penalty_weight`
- `preferred_salary_max_gbp`
- `salary_hard_cap_gbp`
- `salary_penalty_max`
- `care_about_sponsorship`
- `use_sponsor_lookup`

`semantic_profiles` selects which embedding profiles are active for that recipient.
`semantic_profile_texts` can override or add profile text by id.
`negative_profile_texts` is optional extra text describing roles you want pushed down.
`seniority_penalty_weight` controls how strongly those negative profiles affect ranking.
`preferred_salary_max_gbp` is where salary mismatch penalty begins.
`salary_hard_cap_gbp` is where that penalty reaches its maximum.
`salary_penalty_max` controls how much score can be deducted for salary mismatch.
The hard filters are intentionally junior-oriented. Explicit `2+ years` requirements and clearly senior titles are rejected with fixed logic rather than per-recipient tuning.

If you use a custom semantic profile id such as `marketing_assistant` and do not provide
`semantic_profile_texts`, the app now falls back to a simple generated profile text so the run
does not fail. That is acceptable for a quick start, but custom text will usually rank better.

For personalized recipients, the recommended setup is:
- keep your own profile texts for your own recipient entry
- add separate profile texts for the other recipient
- do not rely on the same SWE / Data Science / AI-ML profile text unless that other person genuinely wants the same role targeting

Built-in semantic profile ids:
- `swe`
- `data_science`
- `ai_ml_engineer`

## Sponsorship Lookup

Optional lookup source:
- `SPONSOR_COMPANIES_CSV`
- `SPONSOR_COMPANIES_CSV_TEXT`

Local fallback:
- `sponsor_companies.local.csv`
- `data/uk_sponsors_companies.csv`

Bundled example:
- [examples/sponsor_companies.example.csv](examples/sponsor_companies.example.csv)

The sponsor lookup data can be derived from GOV.UK sponsor register data.
If `data/uk_sponsors_companies.csv` exists in the repo, the app will load it automatically even if `SPONSOR_COMPANIES_CSV` is not set.

Expected CSV schema:

```csv
company_name
example sponsor
```

Only the company column is required.

The lookup is metadata only. It is not a job source.
It is not a live sponsorship check either. The app loads the CSV once per run and matches normalized company names against it in memory.
If enabled for a recipient profile:
- `use_sponsor_lookup` adds a `[Sponsor-licensed]` company marker when the company matches the CSV
- `care_about_sponsorship` adds a `Sponsorship: ...` line only when the job text explicitly or implicitly says something useful

Neither sponsorship option changes ranking or auto-rejects jobs anymore.

Sponsorship classification is rule-based, not embedding-based:
- `explicit_yes`
- `explicit_no`
- `implied_no`
- `unknown`

When sponsorship logic is enabled for a recipient, digests can include:
- `Company [Sponsor-licensed]`
- `Sponsorship: explicit no`
- `Sponsorship: implied no`
- `Sponsorship: explicit yes`

## Target Configuration

Override targets with any of these:
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

Each value can be:
- a JSON array in an environment variable
- a local file such as `ashby_companies.local.json`
- the bundled example seed files in `examples/`

Precedence is:
1. environment variable
2. local file
3. bundled example file

For Ashby and Lever, you can use either a simple slug like `elevenlabs` / `palantir` or a full public board URL. Full URLs are useful when the board uses filtered URLs such as Ashby `locationId=...` or EU Lever boards on `jobs.eu.lever.co`.

The bundled example files contain UK-focused starter targets.
These config files are now the only runtime source of truth for targets. Supabase is no longer used to store or toggle target lists.

## Target Management CLI

You can inspect the effective target config without guessing which file or env var won:

```bash
python manage_targets.py list
python manage_targets.py list ashby
```

The CLI is now read-only. To change hosted targets, update:
- the GitHub Actions variable, if you use one, or
- the committed example file in `examples/`, if you rely on repo defaults

## GitHub Actions Setup

### Required GitHub Secrets

- `JOB_SCRAPER_EMAIL`
- `JOB_SCRAPER_APP_PASSWORD`
- `DATABASE_URL`

### Recommended GitHub Secrets

- `RECIPIENT_PROFILES_JSON`
- `SPONSOR_COMPANIES_CSV_TEXT`

### Optional GitHub Variables

- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`
- `SPONSOR_COMPANIES_CSV`

If you do not set the optional target variables, the workflow reads the bundled example files directly.
If you do set those variables, they override the repo defaults directly.

### Free Postgres Setup

A free Postgres provider like Supabase works well:

1. Create a project.
2. Copy the Postgres connection string.
3. Save it as the `DATABASE_URL` GitHub secret.
4. Run the workflow manually once.

The app creates its tables automatically on first run.

### Easiest GitHub Setup

1. Create your `recipient_profiles.local.json` locally and make sure it works.
2. Copy the full JSON contents.
3. In GitHub go to:
   `Settings -> Secrets and variables -> Actions -> New repository secret`
4. Create a secret named `RECIPIENT_PROFILES_JSON`
5. Paste the JSON text exactly as-is

For sponsorship CSV:

Small CSV:

1. Open the CSV in a text editor
2. Copy the full CSV contents including the header row
3. Create a GitHub secret named `SPONSOR_COMPANIES_CSV_TEXT`
4. Paste the CSV text

Large CSV:

1. Commit the reduced CSV into the repo, for example `data/uk_sponsors_companies.csv`
2. Create a GitHub Actions variable named `SPONSOR_COMPANIES_CSV`
3. Set its value to `data/uk_sponsors_companies.csv`

For larger sponsor lists, the repo file path is the better option.

Typical shared setup:

1. One person owns the repo, secrets, and scheduled workflow
2. That person adds multiple recipient entries to `RECIPIENT_PROFILES_JSON`
3. Each recipient gets their own digest, threshold, and sponsorship preferences
4. The other recipients do not need GitHub accounts, forks, or local setup

## Database Tables

`recipient_seen_jobs`
- stores seen job URLs per recipient profile

Old setups may still contain unused legacy tables such as `scrape_targets` or `seen_jobs`, but the current runtime does not read them.

Safe cleanup order for old tables:
1. deploy the refactor
2. let GitHub Actions complete one successful run on the new code
3. then optionally drop old tables such as `scrape_targets` and `seen_jobs`

Waiting for one successful hosted run first is just a safety check: it confirms the deployed workflow really no longer depends on those tables before you remove them.

## Responsible Use

- Use public job boards only.
- Keep request volume low.
- Respect source terms and policies.
- Do not automate applications or scrape non-public data.
