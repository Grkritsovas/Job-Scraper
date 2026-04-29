# Intended Behavior

This document explains what the main job-scraper features are meant to do in
plain language. It is intentionally about behavior and workflow intent, not a
complete implementation reference.

## Job State And Backlog

The backlog feature itself is simple:

- A job is scraped.
- For each recipient, we classify it:
  - hard filtered: don't store as seen, cheap to reject again
  - semantic below threshold: store as processed/seen, skip next time
  - semantic above threshold but not in top N: store as pending/backlog, support run can pick it up later
  - Gemini failed before reviewing: store as pending/backlog
  - Gemini reviewed/rejected/sent: store as processed/seen
- Extra scheduled runs check: "are there pending backlog jobs?" If no, exit. If yes, run.

The source of truth for this workflow state is `recipient_seen_jobs`
(`app_config.recipient_seen_jobs` on Postgres/Supabase). Despite the historic
table name, it now stores per-recipient job processing state:

- `is_seen=true` means the recipient/job pair should be skipped in future runs.
- `is_seen=false` means the recipient/job pair is pending review and can trigger
  a support run.
- `classification`, `review_family`, `stage`, `run_id`, and score columns explain
  why the row is processed or pending.

Hard-filtered jobs are not stored in this table. They are deterministic and cheap
to reject again, and storing every hard-filtered job would add a lot of low-value
rows.

## Support Runs

The workflow has normal scheduled runs and support scheduled runs.

Normal runs always scrape, rank, review, send, and store state.

Support runs first check the database for recent pending rows in
`recipient_seen_jobs`. If no pending rows exist, the workflow exits before
installing full scraper dependencies. If pending rows exist, the support run
executes the scraper normally. This gives above-threshold jobs that missed the
top-N review cap, or jobs blocked by a temporary Gemini outage, another chance to
be reviewed without manually starting the workflow.

## Review Audit

`recipient_review_audit` (`app_config.recipient_review_audit` on
Postgres/Supabase) is for human inspection. It records compact review history for
semantic decisions, hard-filter samples, and Gemini decisions.

The audit is not the workflow source of truth. It can be pruned for readability
and storage control. The job state table decides whether a recipient/job pair is
skipped or retried.

Audit rows intentionally avoid full recipient profile JSON and full job
descriptions. They keep job metadata, scores, thresholds, categories, concise
Gemini reasons, and short evidence snippets.

## Semantic Matching

Semantic matching is a retrieval layer. Its job is to narrow a large scrape down
to a plausible shortlist before Gemini review.

The semantic stage uses role-focused text rather than the entire posting where
possible. It trims common low-signal sections such as benefits, culture,
diversity statements, legal footers, and application-process boilerplate before
embedding the job text.

The audit stores both:

- `raw_embedding_score`: the embedding similarity before title boosts and salary
  penalties.
- `semantic_score`: the final score after boosts and penalties.

The review UI can sort by either score so borderline retrieval behavior can be
inspected.

## Gemini Review

When `GEMINI_API_KEY` is configured, Gemini review is mandatory for ranked jobs.
There is no semantic fallback if Gemini fails.

Gemini uses a two-pass review:

- pass 1 screens semantic candidates in batches
- pass 2 globally reranks pass-1 approved candidates

Successful Gemini decisions are stored as processed/seen whether the job is sent
or rejected, so the same borderline jobs do not repeatedly return every run.
Temporary Gemini failures are stored as pending/backlog instead.

## Admin UI

`python admin_ui.py` starts a local admin UI for database-backed recipient
profiles and review audit browsing.

The profile editor is schema-shaped rather than free-form JSON. Keys are locked
into the canonical structure, values are editable, and the generated JSON preview
shows what will be saved. This is meant to reduce accidental profile corruption
while still allowing practical profile tuning.

The UI can validate profiles through the same runtime loader used by the scraper,
save profile versions, compare previous versions, and restore older versions.

The UI does not edit GitHub secrets, local recipient JSON files, or job state
rows.
