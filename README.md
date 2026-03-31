# Job Scraper 
### For Entry-Level and Junior Roles in Tech

Scrapes public job boards, ranks roles against configurable profiles, and sends grouped email digests.

Primary intended usage:
- fork the repo
- configure GitHub Actions secrets and variables
- let the scheduled workflow run in GitHub Actions

## What It Does

- loads target companies and boards from config files or GitHub Actions variables
- scrapes jobs from configured public job boards
- ranks jobs separately for each recipient profile with semantic matching (choose a sentence-transformer from [matching/models](matching/models/))
- skips jobs already sent to that recipient
- emails a digest of new matches

Use [examples/README.md](examples/README.md) if you want to inspect the config shapes and starter target files in more detail.

## GitHub Actions Setup

This is the recommended way to use the project.

### Required GitHub Secrets

- `JOB_SCRAPER_EMAIL`
- `JOB_SCRAPER_APP_PASSWORD`
- `DATABASE_URL`
- `RECIPIENT_PROFILES_JSON`

### Optional GitHub Config

- `SPONSOR_COMPANIES_CSV_TEXT`
- `SPONSOR_COMPANIES_CSV`
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

### Setup Steps

1. Fork the repo.
2. Create a Postgres database and save the connection string as `DATABASE_URL`.
3. Add your sender email and app password as `JOB_SCRAPER_EMAIL` and `JOB_SCRAPER_APP_PASSWORD`.
4. Copy the structure from [examples/recipient_profiles.example.json](examples/recipient_profiles.example.json) into `RECIPIENT_PROFILES_JSON`.
5. Optionally override the starter target lists with the GitHub Actions variables above.
6. Optionally add sponsor-company CSV data.
7. Run the workflow manually once, then enable the schedule if you want recurring digests.

If you leave the target variables unset, the workflow uses the bundled starter files in [examples/](examples/).

## Config Overview

### Recipient Profiles

- primary source: `RECIPIENT_PROFILES_JSON`
- local fallback: `recipient_profiles.local.json`
- example: [examples/recipient_profiles.example.json](examples/recipient_profiles.example.json)

Minimum useful fields:
- `id`
- `email`

Everything else is tuning. See [examples/README.md](examples/README.md) for the optional fields.

### Targets

Supported target config variables:
- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

For Greenhouse, `token` here means the public board slug such as `monzo` or `isomorphiclabs`, not a secret or expiring credential.

Lookup order:
1. GitHub Actions variable or environment variable
2. local file such as `ashby_companies.local.json`
3. bundled example file in [examples/](examples/)

The bundled target files are UK-focused starter lists.

### Sponsorship Lookup

Sponsorship lookup is optional and only adds metadata to jobs. It is not a job source and it is not a live sponsorship check.

Supported inputs:
- `SPONSOR_COMPANIES_CSV_TEXT`
- `SPONSOR_COMPANIES_CSV`
- `sponsor_companies.local.csv`
- `data/uk_sponsors_companies.csv`

The CSV only needs a `company_name` column. See [examples/sponsor_companies.example.csv](examples/sponsor_companies.example.csv).

If enabled for a recipient profile:
- `use_sponsor_lookup` adds a `[Sponsor-licensed]` marker when the company matches the CSV
- `care_about_sponsorship` adds a `Sponsorship: ...` line when the job text says something useful

## Local Run (Optional)

Local runs are mainly for testing, debugging, or tuning config before pushing changes.

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Set `JOB_SCRAPER_EMAIL` and `JOB_SCRAPER_APP_PASSWORD`.
4. Optionally set `JOB_SCRAPER_DRY_RUN=1`.
5. Optionally create `recipient_profiles.local.json` and `sponsor_companies.local.csv`.
6. Run `python run_all.py`.

By default, local runs use SQLite in `job_scraper.db`. Hosted runs should use Postgres via `DATABASE_URL`.

## Extra Tools

- `python manage_targets.py list`
- `python manage_targets.py list ashby`

Those commands show the effective target config the app will use.

## Database

`recipient_seen_jobs` stores seen job URLs per recipient profile.

## Acknowledgements

OpenAI Codex / GPT-5.4 for development assistance.

Sample sponsor list from [Borderless](https://uk-sponsors.getborderless.co.uk/sponsors), which states that data is sourced from GOV.UK.

## License

This project is licensed under the [MIT License](LICENSE).

## Responsible Use

- Use public job boards only.
- Keep request volume low.
- Respect source terms and policies.
- Do not automate applications or scrape non-public data.
