from sponsorship import format_sponsorship_summary


def format_company_heading(company, company_jobs, recipient_profile):
    if not recipient_profile.get("use_sponsor_lookup", False):
        return company

    if any(job.get("is_sponsor_licensed_employer") for job in company_jobs):
        return f"{company} [Sponsor-licensed]"

    return company


def _score_to_percent(score):
    return max(0, round(float(score or 0) * 100))


def format_job_fit(job):
    top_profile = job.get("top_profile")
    top_score = job.get("top_score")
    if top_profile and top_score is not None:
        fit_line = f"Fit: {top_profile} {_score_to_percent(top_score)}%"
        second_profile = job.get("second_profile")
        second_score = job.get("second_score")
        if (
            second_profile
            and second_profile != top_profile
            and second_score is not None
            and second_score > 0
        ):
            fit_line += (
                f" | {second_profile} "
                f"{_score_to_percent(second_score)}%"
            )
        return fit_line

    if job.get("fit_summary"):
        return f"Fit: {job['fit_summary']}"

    return ""


def build_digest_bodies(jobs, recipient_profile, max_jobs_per_email=20):
    if not jobs:
        return []

    jobs_by_company = {}
    for job in jobs:
        jobs_by_company.setdefault(job["company"], []).append(job)

    company_blocks = []
    sorted_companies = sorted(
        jobs_by_company,
        key=lambda company: (
            max(
                job.get("ranking_score", job.get("top_score", 0))
                for job in jobs_by_company[company]
            ),
            company.lower(),
        ),
        reverse=True,
    )
    for company in sorted_companies:
        company_jobs = sorted(
            jobs_by_company[company],
            key=lambda job: (
                job.get("ranking_score", job.get("top_score", 0)),
                job.get("top_score", 0),
                job.get("score_margin", 0),
                job["title"].lower(),
                job["url"].lower(),
            ),
            reverse=True,
        )
        lines = [format_company_heading(company, company_jobs, recipient_profile)]
        for job in company_jobs:
            location = job.get("location", "")
            location_suffix = f" | {location}" if location else ""
            lines.append(f"- {job['title']}{location_suffix}")
            fit_line = format_job_fit(job)
            if fit_line:
                lines.append(f"  {fit_line}")
            why_apply = (job.get("why_apply") or "").strip()
            if why_apply:
                lines.append(f"  Why apply: {why_apply}")
            if recipient_profile.get("care_about_sponsorship", False):
                sponsorship_summary = format_sponsorship_summary(job)
                if sponsorship_summary:
                    lines.append(f"  {sponsorship_summary}")
            lines.append(job["url"])
        company_blocks.append((len(company_jobs), "\n".join(lines)))

    bodies = []
    current_blocks = []
    current_count = 0

    for block_count, block_text in company_blocks:
        if current_blocks and current_count + block_count > max_jobs_per_email:
            bodies.append("\n\n".join(current_blocks))
            current_blocks = []
            current_count = 0

        current_blocks.append(block_text)
        current_count += block_count

    if current_blocks:
        bodies.append("\n\n".join(current_blocks))

    return bodies
