# Job Scraper

Scrapes public job boards, filters roles by your own title/location/experience rules, and sends grouped email digests.

Current sources:
- Ashby public job boards
- Greenhouse Job Board API
- Lever Postings API
- Site-specific Next.js `__NEXT_DATA__` pages

## How It Works

- Targets come from environment variables, local JSON files, or bundled example seed files.
- Seen-job state is stored in a database.
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

5. Run:

```bash
python run_all.py
```

This creates `job_scraper.db` locally unless you set `DATABASE_URL`.
That local SQLite file is enough for repeated runs on your own machine.

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

### Target Management CLI

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

### Optional GitHub Variables

- `ASHBY_COMPANIES_JSON`
- `GREENHOUSE_BOARD_TOKENS_JSON`
- `LEVER_COMPANIES_JSON`
- `NEXTJS_URLS_JSON`

If you do not set the optional variables, the workflow seeds from the bundled example files.

### Free Postgres Setup

A free Postgres provider like Supabase works well:

1. Create a project.
2. Copy the Postgres connection string.
3. Save it as the `DATABASE_URL` GitHub secret.
4. Run the workflow manually once.

The app creates the tables automatically on first run.

## Greenhouse Notes

Greenhouse support uses the public Job Board API. You still need a board token or board URL per company. There is no supported API to enumerate every Greenhouse company globally.

Examples:
- `koboldmetals`
- `https://job-boards.greenhouse.io/hudl`

## Database Tables

`scrape_targets`
- stores target values per source
- allows future manual enable/disable control

`seen_jobs`
- stores job URLs that have already triggered notifications

## Responsible Use

- Use public job boards only.
- Keep request volume low.
- Respect source terms and policies.
- Do not automate applications or scrape non-public data.
