# Job Scraper

Scrapes public job boards, semantically ranks roles against configurable profiles, and sends grouped email digests.

Current sources:
- Ashby public job boards
- Greenhouse Job Board API
- Lever Postings API
- Site-specific Next.js `__NEXT_DATA__` pages

## How It Works

- Targets come from environment variables, local JSON files, or bundled example seed files.
- Jobs are scraped once per run, then enriched once with sponsorship metadata.
- Recipient profiles are loaded from config and scored independently.
- Seen-job state is stored in a database per recipient profile.
- Local runs use SQLite by default in `job_scraper.db`.
- Hosted runs should use Postgres via `DATABASE_URL`.

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

6. Run:

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

Example shape:

```json
[
  {
    "id": "george",
    "email": "you@example.com",
    "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
    "min_top_score": 0.45,
    "care_about_sponsorship": false,
    "use_sponsor_lookup": false
  },
  {
    "id": "elisabeth",
    "email": "other@example.com",
    "semantic_profiles": ["swe", "data_science", "ai_ml_engineer"],
    "min_top_score": 0.45,
    "care_about_sponsorship": true,
    "use_sponsor_lookup": true
  }
]
```

Supported recipient fields:
- `id`
- `email`
- `semantic_profiles`
- `semantic_profile_texts`
- `min_top_score`
- `care_about_sponsorship`
- `use_sponsor_lookup`

`semantic_profiles` selects which embedding profiles are active for that recipient.
`semantic_profile_texts` can override or add profile text by id.

Built-in semantic profile ids:
- `swe`
- `data_science`
- `ai_ml_engineer`

## Sponsorship Lookup

Optional lookup source:
- `SPONSOR_COMPANIES_CSV`

Local fallback:
- `sponsor_companies.local.csv`

Bundled example:
- [examples/sponsor_companies.example.csv](examples/sponsor_companies.example.csv)

Expected CSV schema:

```csv
company_name
Example Sponsor Ltd
Example Sponsor Plc
```

The lookup is metadata only. It is not a job source.
If enabled for a recipient profile:
- sponsor-licensed employers get a small positive prior
- `explicit_no` sponsorship wording still wins and blocks the role

Sponsorship classification is rule-based, not embedding-based:
- `explicit_yes`
- `explicit_no`
- `implied_no`
- `unknown`

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

The bundled example files contain UK-focused starter targets.

## Target Management CLI

You can manage database-backed targets without editing SQL directly:

```bash
python manage_targets.py list
python manage_targets.py add greenhouse https://job-boards.greenhouse.io/koboldmetals
python manage_targets.py disable ashby multiverse
```

## GitHub Actions Setup

### Required GitHub Secrets

- `JOB_SCRAPER_EMAIL`
- `JOB_SCRAPER_APP_PASSWORD`
- `DATABASE_URL`

### Recommended GitHub Secrets

- `RECIPIENT_PROFILES_JSON`

### Optional GitHub Variables

- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`
- `SPONSOR_COMPANIES_CSV`

If you do not set the optional target variables, the workflow seeds from the bundled example files.

### Free Postgres Setup

A free Postgres provider like Supabase works well:

1. Create a project.
2. Copy the Postgres connection string.
3. Save it as the `DATABASE_URL` GitHub secret.
4. Run the workflow manually once.

The app creates its tables automatically on first run.

## Database Tables

`scrape_targets`
- stores target values per source
- allows manual enable/disable control

`recipient_seen_jobs`
- stores seen job URLs per recipient profile

`seen_jobs`
- older shared seen-job table
- still read as legacy seed data for existing setups

## Responsible Use

- Use public job boards only.
- Keep request volume low.
- Respect source terms and policies.
- Do not automate applications or scrape non-public data.
