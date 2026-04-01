from html import escape

from sponsorship import format_sponsorship_summary


def format_company_heading(company, company_jobs, recipient_profile):
    if not recipient_profile.get("use_sponsor_lookup", False):
        return company

    if any(job.get("is_sponsor_licensed_employer") for job in company_jobs):
        return f"{company} [Sponsor-licensed]"

    return company


def _score_to_percent(score):
    return max(0, round(float(score or 0) * 100))


def _job_primary_score(job):
    return job.get("ranking_score", job.get("top_score", 0))


def _sort_company_jobs(company_jobs):
    return sorted(
        company_jobs,
        key=lambda job: (
            _job_primary_score(job),
            job.get("top_score", 0),
            job.get("score_margin", 0),
            job["title"].lower(),
            job["url"].lower(),
        ),
        reverse=True,
    )


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


def _group_jobs_by_company(jobs, recipient_profile):
    jobs_by_company = {}
    for job in jobs:
        jobs_by_company.setdefault(job["company"], []).append(job)

    sorted_companies = sorted(
        jobs_by_company,
        key=lambda company: (
            max(_job_primary_score(job) for job in jobs_by_company[company]),
            company.lower(),
        ),
        reverse=True,
    )

    grouped = []
    for company in sorted_companies:
        company_jobs = _sort_company_jobs(jobs_by_company[company])
        grouped.append(
            {
                "company_heading": format_company_heading(
                    company,
                    company_jobs,
                    recipient_profile,
                ),
                "jobs": company_jobs,
            }
        )
    return grouped


def _chunk_company_groups(company_groups, max_jobs_per_email):
    chunks = []
    current_chunk = []
    current_count = 0

    for group in company_groups:
        group_count = len(group["jobs"])
        if current_chunk and current_count + group_count > max_jobs_per_email:
            chunks.append(current_chunk)
            current_chunk = []
            current_count = 0

        current_chunk.append(group)
        current_count += group_count

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _build_digest_chunks(jobs, recipient_profile, max_jobs_per_email=20):
    if not jobs:
        return []

    company_groups = _group_jobs_by_company(jobs, recipient_profile)
    return _chunk_company_groups(company_groups, max_jobs_per_email)


def _render_text_chunk(company_groups, recipient_profile):
    blocks = []
    for group in company_groups:
        lines = [group["company_heading"]]
        for job in group["jobs"]:
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
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _score_theme(job):
    score = _job_primary_score(job)
    if score >= 0.8:
        return {
            "label": "Strong Match",
            "solid": "#0f766e",
            "gradient": "linear-gradient(135deg, #0f766e 0%, #14b8a6 100%)",
            "badge_bg": "#ccfbf1",
            "badge_text": "#115e59",
            "border": "#99f6e4",
        }
    if score >= 0.65:
        return {
            "label": "Good Match",
            "solid": "#1d4ed8",
            "gradient": "linear-gradient(135deg, #1d4ed8 0%, #38bdf8 100%)",
            "badge_bg": "#dbeafe",
            "badge_text": "#1e3a8a",
            "border": "#bfdbfe",
        }
    if score >= 0.5:
        return {
            "label": "Borderline",
            "solid": "#7c3aed",
            "gradient": "linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)",
            "badge_bg": "#ede9fe",
            "badge_text": "#5b21b6",
            "border": "#ddd6fe",
        }
    return {
        "label": "Borderline",
        "solid": "#475569",
        "gradient": "linear-gradient(135deg, #475569 0%, #94a3b8 100%)",
        "badge_bg": "#e2e8f0",
        "badge_text": "#334155",
        "border": "#cbd5e1",
    }


def _render_job_card_html(job, recipient_profile):
    title = escape(job.get("title", ""))
    company = escape(job.get("company", ""))
    location = escape(job.get("location", ""))
    url = escape(job.get("url", ""))
    fit_line = format_job_fit(job)
    why_apply = (job.get("why_apply") or "").strip()
    sponsorship_summary = (
        format_sponsorship_summary(job)
        if recipient_profile.get("care_about_sponsorship", False)
        else ""
    )
    theme = _score_theme(job)

    meta_bits = []
    if location:
        meta_bits.append(
            f"<span style=\"display:inline-block;margin-right:8px;\">{location}</span>"
        )
    if fit_line:
        meta_bits.append(
            f"<span style=\"display:inline-block;\">{escape(fit_line)}</span>"
        )
    meta_html = ""
    if meta_bits:
        meta_html = (
            "<div style=\"margin-top:10px;color:#475569;font-size:13px;line-height:1.6;\">"
            + " ".join(meta_bits)
            + "</div>"
        )

    why_html = ""
    if why_apply:
        why_html = (
            "<div style=\"margin-top:14px;padding:12px 14px;border-radius:14px;"
            "background:#f8fafc;color:#0f172a;font-size:14px;line-height:1.6;\">"
            f"<strong style=\"font-weight:700;\">Why apply:</strong> {escape(why_apply)}"
            "</div>"
        )

    sponsorship_html = ""
    if sponsorship_summary:
        sponsorship_html = (
            "<div style=\"margin-top:12px;color:#92400e;font-size:13px;line-height:1.5;\">"
            f"{escape(sponsorship_summary)}"
            "</div>"
        )

    return (
        "<div style=\"margin-top:14px;background:#ffffff;border:1px solid "
        f"{theme['border']};border-radius:20px;overflow:hidden;\">"
        f"<div style=\"height:6px;background:{theme['solid']};background-image:{theme['gradient']};\"></div>"
        "<div style=\"padding:18px 18px 20px 18px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr>"
        f"<td style=\"vertical-align:top;padding-right:12px;\">"
        f"<div style=\"font-size:13px;color:#64748b;line-height:1.4;\">{company}</div>"
        f"<div style=\"margin-top:4px;font-size:20px;line-height:1.3;color:#0f172a;font-weight:700;\">{title}</div>"
        f"{meta_html}"
        f"{why_html}"
        f"{sponsorship_html}"
        "</td>"
        "<td style=\"vertical-align:top;text-align:right;white-space:nowrap;\">"
        f"<div style=\"display:inline-block;padding:8px 12px;border-radius:999px;"
        f"background:{theme['badge_bg']};color:{theme['badge_text']};font-size:12px;"
        f"font-weight:700;letter-spacing:0.02em;\">{escape(theme['label'])}</div>"
        "</td>"
        "</tr>"
        "</table>"
        "<div style=\"margin-top:16px;\">"
        f"<a href=\"{url}\" "
        "style=\"display:inline-block;padding:11px 18px;border-radius:12px;"
        "background:#2563eb;color:#ffffff;text-decoration:none;font-size:14px;"
        "font-weight:700;\">Open Role</a>"
        "</div>"
        "</div>"
        "</div>"
    )


def _render_html_chunk(company_groups, recipient_profile, total_jobs):
    company_sections = []
    for group in company_groups:
        jobs_html = "".join(
            _render_job_card_html(job, recipient_profile) for job in group["jobs"]
        )
        company_sections.append(
            "<div style=\"margin-top:24px;\">"
            f"<div style=\"font-size:18px;line-height:1.3;color:#0f172a;font-weight:800;\">"
            f"{escape(group['company_heading'])}"
            "</div>"
            f"{jobs_html}"
            "</div>"
        )

    sections_html = "".join(company_sections)
    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\">"
        "<body style=\"margin:0;padding:0;background:#eef2ff;font-family:Segoe UI,Arial,sans-serif;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        "style=\"background:#eef2ff;\">"
        "<tr><td align=\"center\" style=\"padding:24px 12px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        "style=\"max-width:760px;background:#ffffff;border-radius:28px;overflow:hidden;\">"
        "<tr><td style=\"padding:0;\">"
        "<div style=\"padding:28px 28px 24px 28px;background:#0f172a;"
        "background-image:linear-gradient(135deg, #0f172a 0%, #1d4ed8 52%, #38bdf8 100%);\">"
        "<div style=\"display:inline-block;padding:7px 12px;border-radius:999px;"
        "background:rgba(255,255,255,0.16);color:#dbeafe;font-size:12px;font-weight:700;"
        "letter-spacing:0.05em;text-transform:uppercase;\">Job Digest</div>"
        "<div style=\"margin-top:14px;font-size:30px;line-height:1.2;color:#ffffff;font-weight:800;\">"
        "New roles worth a look"
        "</div>"
        f"<div style=\"margin-top:10px;font-size:15px;line-height:1.6;color:#dbeafe;\">"
        f"{total_jobs} match{'es' if total_jobs != 1 else ''} in this digest. "
        "The strongest roles appear first."
        "</div>"
        "</div>"
        "</td></tr>"
        "<tr><td style=\"padding:24px 24px 30px 24px;background:#f8fafc;\">"
        f"{sections_html}"
        "<div style=\"margin-top:28px;font-size:12px;line-height:1.6;color:#64748b;\">"
        "This email includes an HTML view for easier scanning. A plain-text version is attached as fallback."
        "</div>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )


def build_digest_payloads(jobs, recipient_profile, max_jobs_per_email=20):
    chunks = _build_digest_chunks(jobs, recipient_profile, max_jobs_per_email)
    if not chunks:
        return []

    total_jobs = len(jobs)
    return [
        {
            "text": _render_text_chunk(chunk, recipient_profile),
            "html": _render_html_chunk(chunk, recipient_profile, total_jobs),
        }
        for chunk in chunks
    ]


def build_digest_bodies(jobs, recipient_profile, max_jobs_per_email=20):
    return [
        payload["text"]
        for payload in build_digest_payloads(
            jobs,
            recipient_profile,
            max_jobs_per_email=max_jobs_per_email,
        )
    ]


def build_digest_html_bodies(jobs, recipient_profile, max_jobs_per_email=20):
    return [
        payload["html"]
        for payload in build_digest_payloads(
            jobs,
            recipient_profile,
            max_jobs_per_email=max_jobs_per_email,
        )
    ]
