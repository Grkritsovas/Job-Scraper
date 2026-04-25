import json
import os
import re
import threading
import time

from matching.profile_library import build_profile_specs
from shared.descriptions import normalize_text_whitespace, strip_matching_boilerplate


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_TOP_N = 100
DEFAULT_BATCH_SIZE = 10
DEFAULT_DESCRIPTION_CHARS = 1600
DEFAULT_EVIDENCE_ITEMS = 2
DEFAULT_MAX_SEMANTIC_EMAIL_JOBS = 60
DEFAULT_GEMINI_RETRY_ATTEMPTS = 20
DEFAULT_GEMINI_RETRY_BASE_SECONDS = 5.0
GEMINI_RETRY_MAX_DELAY_SECONDS = 60.0
GEMINI_RETRY_TOTAL_WAIT_SECONDS = 600.0
GEMINI_CONCURRENCY_CAP = 4
RETRYABLE_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}
RETRYABLE_GEMINI_ERROR_MARKERS = (
    "deadline exceeded",
    "internal error",
    "rate limit",
    "resource exhausted",
    "service unavailable",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "unavailable",
)
_GEMINI_CALL_LIMITER = threading.BoundedSemaphore(GEMINI_CONCURRENCY_CAP)
PASS_ONE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_url": {"type": "string"},
                    "matched_profile": {"type": "string"},
                    "fit_score": {"type": "integer"},
                    "why_apply": {"type": "string"},
                    "supporting_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "mismatch_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "job_url",
                    "matched_profile",
                    "fit_score",
                    "why_apply",
                    "supporting_evidence",
                    "mismatch_evidence",
                ],
            },
        }
    },
    "required": ["candidates"],
}
PASS_TWO_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "shortlisted_jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_url": {"type": "string"},
                    "fit_score": {"type": "integer"},
                    "why_apply": {"type": "string"},
                },
                "required": ["job_url", "fit_score", "why_apply"],
            },
        }
    },
    "required": ["shortlisted_jobs"],
}


def gemini_rerank_enabled():
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def _safe_int_env(name, default):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError:
        return default


def _safe_float_env(name, default):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _build_result(
    jobs_to_send,
    reviewed_jobs,
    review_mode,
    llm_shortlisted_jobs=None,
    gemini_reviewed_jobs=None,
    review_error=None,
    review_error_stage=None,
):
    return {
        "jobs_to_send": jobs_to_send,
        "reviewed_jobs": reviewed_jobs,
        "review_mode": review_mode,
        "llm_shortlisted_jobs": llm_shortlisted_jobs,
        "gemini_reviewed_jobs": gemini_reviewed_jobs,
        "review_error": review_error,
        "review_error_stage": review_error_stage,
    }


def _chunked(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _trim_description(description, limit):
    trimmed = normalize_text_whitespace(strip_matching_boilerplate(description))
    if len(trimmed) <= limit:
        return trimmed

    candidate = trimmed[:limit].rsplit(" ", 1)[0].strip()
    return candidate or trimmed[:limit].strip()


def _fit_hint(job):
    top_profile = job.get("top_profile")
    top_score = job.get("top_score")
    if not top_profile or top_score is None:
        return job.get("fit_summary", "")

    parts = [f"{top_profile} {round(float(top_score) * 100)}%"]
    second_profile = job.get("second_profile")
    second_score = job.get("second_score")
    if (
        second_profile
        and second_profile != top_profile
        and second_score is not None
        and second_score > 0
    ):
        parts.append(f"{second_profile} {round(float(second_score) * 100)}%")

    return " | ".join(parts)


def _build_job_payload(job, description_chars):
    payload = {
        "url": job.get("url", ""),
        "company": normalize_text_whitespace(job.get("company", "")),
        "title": normalize_text_whitespace(job.get("title", "")),
        "location": normalize_text_whitespace(job.get("location", "")),
        "semantic_fit_hint": _fit_hint(job),
        "description_excerpt": _trim_description(
            job.get("description", ""),
            description_chars,
        ),
    }
    if job.get("salary_upper_bound_gbp") is not None:
        payload["salary_upper_bound_gbp"] = job.get("salary_upper_bound_gbp")
    return payload


def _build_candidate_context(recipient_profile):
    profiles = [
        {
            "label": spec["label"],
            "text": normalize_text_whitespace(spec["text"]),
        }
        for spec in build_profile_specs(recipient_profile)
    ]
    context = {
        "target_profiles": profiles,
        "cv_summary": normalize_text_whitespace(recipient_profile.get("cv_summary", "")),
    }
    education_status = normalize_text_whitespace(
        recipient_profile.get("education_status", "")
    )
    if education_status:
        context["education_status"] = education_status
    work_authorization_summary = normalize_text_whitespace(
        recipient_profile.get("work_authorization_summary", "")
    )
    if work_authorization_summary:
        context["work_authorization_summary"] = work_authorization_summary
    if recipient_profile.get("preferred_salary_max_gbp") is not None:
        context["preferred_salary_max_gbp"] = recipient_profile.get(
            "preferred_salary_max_gbp"
        )
    if recipient_profile.get("salary_hard_cap_gbp") is not None:
        context["salary_hard_cap_gbp"] = recipient_profile.get("salary_hard_cap_gbp")
    return context


def _add_salary_rule(instructions, recipient_profile):
    preferred_salary_max = recipient_profile.get("preferred_salary_max_gbp")
    if preferred_salary_max is None:
        return

    instructions["salary_rule"] = (
        "If salary context is provided, prefer roles whose compensation does not "
        "clearly exceed the candidate's target range. Treat roles far above the "
        "preferred salary as weaker matches, even when the skills overlap."
    )


def _add_extra_guidance(instructions, key, guidance_items):
    cleaned = [
        normalize_text_whitespace(item)
        for item in (guidance_items or [])
        if normalize_text_whitespace(item)
    ]
    if cleaned:
        instructions[key] = cleaned


def _build_pass_one_prompt(recipient_profile, jobs, description_chars):
    instructions = {
        "primary_source_of_truth": (
            "The target profiles are the main decision rule. "
            "A job must clearly fit at least one target profile to be kept."
        ),
        "cv_usage": (
            "The CV summary is supporting context only. "
            "Use it to judge transferable evidence, not to override the target profiles."
        ),
        "employability_rule": (
            "Focus on realistic employability today. "
            "Do not keep a role unless this candidate could plausibly be hired for it now."
        ),
        "selection_rule": (
            "False positives are worse than false negatives. "
            "Do not keep a role unless the fit is clear."
        ),
        "bad_match_example": (
            "Bad match example: Quantitative Freight Analyst - Dry Bulk for an "
            "early-career Computer Science and AI graduate. Shared signals like "
            "Python, forecasting, analytics, or machine learning are not enough "
            "when the role expects an experienced quantitative analyst with "
            "specialist freight-market ownership and domain depth."
        ),
        "scope_rule": (
            "Reject roles whose scope, title, or description indicate seniority, "
            "independent ownership, management, strategy, consulting, or specialist "
            "domain expertise beyond the candidate's evidence."
        ),
        "title_rule": (
            "Be especially cautious with titles like manager, lead, senior, staff, "
            "principal, director, strategist, consultant, partner, or specialist."
        ),
        "domain_depth_rule": (
            "Reject roles that depend on existing niche domain depth, such as freight, "
            "quant finance, maritime, or other specialist commercial knowledge not "
            "supported by the candidate context."
        ),
        "infrastructure_scope_rule": (
            "Reject infrastructure, SRE, platform, cloud operations, and internal tooling "
            "roles when Kubernetes, Terraform, CI/CD ownership, observability, incident "
            "response, 24x7 on-call, GPU clusters, or cloud operations are core duties, "
            "unless the target profiles explicitly include that infrastructure scope."
        ),
        "comparison_rule": (
            "Judge each role on its own merits. "
            "If none are clearly good, return an empty list."
        ),
        "evidence_rule": (
            "supporting_evidence and mismatch_evidence must contain short exact or "
            "near-exact snippets from the provided job text."
        ),
        "profile_rule": (
            "matched_profile must be exactly one of the provided target profile labels."
        ),
        "level_preference": (
            "Prefer junior, graduate, grad, and entry-level roles. "
            "Be cautious with manager, lead, senior, and staff roles."
        ),
        "student_programme_rule": (
            "Use candidate education_status when screening internships, placements, "
            "and student programmes. Reject roles only when the job text explicitly "
            "requires current-student status, current enrollment, returning to study, "
            "or a future graduation date that the candidate does not meet. Do not "
            "reject an internship merely because student status is unspecified; judge "
            "the rest of the role fit normally."
        ),
        "output_rule": (
            "Return only credible candidates. "
            "For why_apply, write at most 2 short simple sentences."
        ),
    }
    if recipient_profile.get("care_about_hard_eligibility", False):
        instructions["eligibility_rule"] = (
            "Reject roles with hard eligibility requirements the candidate is unlikely to meet. "
            "This includes SC clearance, DV clearance, security vetting, nationality or citizenship restrictions, "
            "and explicit continuous UK residency requirements such as 3 years, 5 years, or similar. "
            "Use work_authorization_summary when provided. Do not keep these roles unless "
            "the candidate context directly confirms eligibility. If work_authorization_summary "
            "mentions time-limited authorization or a visa expiry, treat explicit no-sponsorship "
            "language as a significant mismatch for roles that appear to require work beyond "
            "that authorization window, but do not reject solely because sponsorship is unstated."
        )
    _add_salary_rule(instructions, recipient_profile)
    _add_extra_guidance(
        instructions,
        "extra_screening_guidance",
        recipient_profile.get("extra_screening_guidance"),
    )

    candidate_payload = {
        "instructions": instructions,
        "candidate": _build_candidate_context(recipient_profile),
        "jobs": [_build_job_payload(job, description_chars) for job in jobs],
    }
    return (
        "Screen these jobs for one candidate. "
        "Return only credible candidates as JSON matching the schema.\n\n"
        f"{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}"
    )


def _build_pass_two_prompt(recipient_profile, candidates):
    candidate_cards = [
        {
            "url": candidate["url"],
            "company": normalize_text_whitespace(candidate.get("company", "")),
            "title": normalize_text_whitespace(candidate.get("title", "")),
            "location": normalize_text_whitespace(candidate.get("location", "")),
            "salary_upper_bound_gbp": candidate.get("salary_upper_bound_gbp"),
            "matched_profile": candidate.get("llm_matched_profile", ""),
            "batch_fit_score": candidate.get("llm_fit_score", 0),
            "semantic_fit_hint": _fit_hint(candidate),
            "why_apply": normalize_text_whitespace(candidate.get("why_apply", "")),
            "supporting_evidence": list(candidate.get("supporting_evidence", [])),
            "mismatch_evidence": list(candidate.get("mismatch_evidence", [])),
        }
        for candidate in candidates
    ]
    instructions = {
        "task": (
            "Compare these already-screened candidates globally and keep only the "
            "strongest final matches."
        ),
        "employability_rule": (
            "Focus on realistic employability today. "
            "Drop roles that only look relevant because of tool overlap."
        ),
        "selection_rule": (
            "False positives are worse than false negatives. "
            "If none are clearly strong matches, return an empty list."
        ),
        "scope_rule": (
            "Reject roles whose final case depends on stretched reasoning, domain-specific "
            "ownership, or seniority the candidate does not clearly have."
        ),
        "infrastructure_scope_rule": (
            "Drop infrastructure, SRE, platform, cloud operations, and internal tooling "
            "roles when Kubernetes, Terraform, CI/CD ownership, observability, incident "
            "response, 24x7 on-call, GPU clusters, or cloud operations are core duties, "
            "unless the target profiles explicitly include that infrastructure scope."
        ),
        "bad_match_example": (
            "Example to reject: Quantitative Freight Analyst - Dry Bulk for an "
            "early-career Computer Science and AI graduate. Shared Python, forecasting, "
            "or analytics overlap is not enough when the role expects experienced "
            "quantitative ownership and freight-market depth."
        ),
        "comparison_rule": (
            "Use the candidate profiles as the main rule. "
            "Jobs with weak evidence, notable mismatches, or stretched reasoning should be dropped."
        ),
        "student_programme_rule": (
            "Use candidate education_status when comparing internships, placements, "
            "and student programmes. Drop roles only when the job text explicitly "
            "requires current-student status, current enrollment, returning to study, "
            "or a future graduation date that the candidate does not meet. Do not "
            "drop an internship merely because student status is unspecified; compare "
            "the rest of the role fit normally."
        ),
        "output_rule": (
            "Return only the final shortlist as JSON matching the schema. "
            "For why_apply, write at most 2 short simple sentences."
        ),
    }
    if recipient_profile.get("care_about_hard_eligibility", False):
        instructions["eligibility_rule"] = (
            "Reject roles with hard eligibility requirements the candidate is unlikely to meet. "
            "This includes SC clearance, DV clearance, security vetting, nationality or citizenship restrictions, "
            "and explicit continuous UK residency requirements such as 3 years, 5 years, or similar. "
            "Use work_authorization_summary when provided. Do not keep these roles unless "
            "the candidate context directly confirms eligibility. If work_authorization_summary "
            "mentions time-limited authorization or a visa expiry, treat explicit no-sponsorship "
            "language as a significant mismatch for roles that appear to require work beyond "
            "that authorization window, but do not reject solely because sponsorship is unstated."
        )
    _add_salary_rule(instructions, recipient_profile)
    _add_extra_guidance(
        instructions,
        "extra_final_ranking_guidance",
        recipient_profile.get("extra_final_ranking_guidance"),
    )

    payload = {
        "instructions": instructions,
        "candidate": _build_candidate_context(recipient_profile),
        "screened_candidates": candidate_cards,
    }
    return (
        "Finalize the shortlist for one candidate. "
        "These jobs already passed a first screening round. "
        "Now compare them against each other and keep only the genuinely strong matches.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _build_client(api_key=None):
    effective_api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not effective_api_key:
        return None

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Gemini reranking requires google-genai. Install dependencies from requirements.txt."
        ) from exc

    return genai.Client(api_key=effective_api_key)


def _extract_error_status_codes(error):
    candidates = [
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(error, "status", None),
    ]
    response = getattr(error, "response", None)
    if response is not None:
        candidates.append(getattr(response, "status_code", None))

    codes = set()
    for candidate in candidates:
        if isinstance(candidate, int):
            codes.add(candidate)
            continue
        if isinstance(candidate, str) and candidate.isdigit():
            codes.add(int(candidate))

    for match in re.finditer(r"\b(429|500|502|503|504)\b", str(error)):
        codes.add(int(match.group(1)))

    return codes


def _is_retryable_gemini_error(error):
    if _extract_error_status_codes(error) & RETRYABLE_GEMINI_STATUS_CODES:
        return True

    normalized_message = normalize_text_whitespace(str(error)).lower()
    return any(marker in normalized_message for marker in RETRYABLE_GEMINI_ERROR_MARKERS)


def _generate_json_response(client, model, prompt, schema, retry_deadline=None):
    retry_attempts = max(
        1,
        _safe_int_env(
            "JOB_SCRAPER_LLM_RETRY_ATTEMPTS",
            DEFAULT_GEMINI_RETRY_ATTEMPTS,
        ),
    )
    retry_base_seconds = max(
        0.0,
        _safe_float_env(
            "JOB_SCRAPER_LLM_RETRY_BASE_SECONDS",
            DEFAULT_GEMINI_RETRY_BASE_SECONDS,
        ),
    )

    for attempt_index in range(retry_attempts):
        try:
            with _GEMINI_CALL_LIMITER:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_json_schema": schema,
                    },
                )
            return json.loads(getattr(response, "text", "") or "{}")
        except Exception as exc:
            is_last_attempt = attempt_index == retry_attempts - 1
            if is_last_attempt or not _is_retryable_gemini_error(exc):
                raise

            retry_number = attempt_index + 1
            retry_delay = min(
                retry_base_seconds * (2**attempt_index),
                GEMINI_RETRY_MAX_DELAY_SECONDS,
            )
            remaining_retry_budget = None
            if retry_deadline is not None:
                remaining_retry_budget = retry_deadline - time.monotonic()
                if remaining_retry_budget <= 0:
                    raise
                retry_delay = min(retry_delay, remaining_retry_budget)

            remaining_budget_suffix = ""
            if remaining_retry_budget is not None:
                remaining_budget_suffix = (
                    f" Remaining retry budget {remaining_retry_budget:.1f}s."
                )
            print(
                "Warning: Gemini API call failed with a retryable error. "
                f"Retrying {retry_number}/{retry_attempts - 1} in {retry_delay:.1f}s. "
                f"{exc}.{remaining_budget_suffix}"
            )
            if retry_delay > 0:
                time.sleep(retry_delay)

    raise RuntimeError("Gemini API retry loop exited unexpectedly.")


def _normalize_string_list(values):
    if not isinstance(values, list):
        return []

    normalized = []
    for value in values[:DEFAULT_EVIDENCE_ITEMS]:
        cleaned = normalize_text_whitespace(value)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _run_batch_screening(
    candidate_jobs,
    recipient_profile,
    client,
    model,
    batch_size,
    description_chars,
    retry_deadline,
):
    original_indexes = {
        job["url"]: index
        for index, job in enumerate(candidate_jobs)
        if job.get("url")
    }
    screened_candidates = []
    seen_urls = set()

    for batch in _chunked(candidate_jobs, batch_size):
        batch_by_url = {
            job["url"]: job
            for job in batch
            if job.get("url")
        }
        prompt = _build_pass_one_prompt(
            recipient_profile,
            batch,
            description_chars,
        )
        payload = _generate_json_response(
            client,
            model,
            prompt,
            PASS_ONE_JSON_SCHEMA,
            retry_deadline=retry_deadline,
        )
        for item in payload.get("candidates", []):
            job_url = normalize_text_whitespace(item.get("job_url", ""))
            if not job_url or job_url in seen_urls or job_url not in batch_by_url:
                continue

            matched_profile = normalize_text_whitespace(item.get("matched_profile", ""))
            if not matched_profile:
                continue

            try:
                fit_score = int(item.get("fit_score", 0))
            except (TypeError, ValueError):
                fit_score = 0
            fit_score = max(0, min(100, fit_score))
            why_apply = normalize_text_whitespace(item.get("why_apply", ""))
            supporting_evidence = _normalize_string_list(item.get("supporting_evidence"))
            mismatch_evidence = _normalize_string_list(item.get("mismatch_evidence"))

            original_job = batch_by_url[job_url]
            screened_candidates.append(
                {
                    **original_job,
                    "semantic_ranking_score": original_job.get("ranking_score"),
                    "llm_matched_profile": matched_profile,
                    "ranking_score": fit_score / 100.0,
                    "llm_fit_score": fit_score,
                    "why_apply": why_apply,
                    "supporting_evidence": supporting_evidence,
                    "mismatch_evidence": mismatch_evidence,
                    "_original_index": original_indexes.get(job_url, 10**9),
                }
            )
            seen_urls.add(job_url)

    screened_candidates.sort(
        key=lambda job: (
            -job.get("llm_fit_score", 0),
            job.get("_original_index", 10**9),
        )
    )
    return screened_candidates


def _run_final_rerank(candidates, recipient_profile, client, model, retry_deadline):
    if not candidates:
        return []

    candidates_by_url = {
        candidate["url"]: candidate
        for candidate in candidates
        if candidate.get("url")
    }
    prompt = _build_pass_two_prompt(recipient_profile, candidates)
    payload = _generate_json_response(
        client,
        model,
        prompt,
        PASS_TWO_JSON_SCHEMA,
        retry_deadline=retry_deadline,
    )
    final_shortlist = []
    seen_urls = set()

    for item in payload.get("shortlisted_jobs", []):
        job_url = normalize_text_whitespace(item.get("job_url", ""))
        if not job_url or job_url in seen_urls or job_url not in candidates_by_url:
            continue

        try:
            fit_score = int(item.get("fit_score", 0))
        except (TypeError, ValueError):
            fit_score = 0
        fit_score = max(0, min(100, fit_score))
        why_apply = normalize_text_whitespace(item.get("why_apply", ""))

        original_candidate = candidates_by_url[job_url]
        final_shortlist.append(
            {
                **original_candidate,
                "ranking_score": fit_score / 100.0,
                "llm_fit_score": fit_score,
                "why_apply": why_apply or original_candidate.get("why_apply", ""),
            }
        )
        seen_urls.add(job_url)

    final_shortlist.sort(
        key=lambda job: (
            -job.get("llm_fit_score", 0),
            job.get("_original_index", 10**9),
        )
    )
    return final_shortlist


def _strip_internal_fields(jobs):
    return [
        {
            key: value
            for key, value in job.items()
            if not key.startswith("_")
        }
        for job in jobs
    ]


def rerank_jobs_with_gemini(
    jobs,
    recipient_profile,
    client=None,
    model=None,
    top_n=None,
    batch_size=None,
    description_chars=None,
):
    if not jobs:
        return _build_result([], [], "empty", llm_shortlisted_jobs=0, gemini_reviewed_jobs=0)

    if not gemini_rerank_enabled():
        max_semantic_email_jobs = max(
            1,
            _safe_int_env(
                "JOB_SCRAPER_MAX_SEMANTIC_EMAIL_JOBS",
                DEFAULT_MAX_SEMANTIC_EMAIL_JOBS,
            ),
        )
        semantic_jobs = jobs[:max_semantic_email_jobs]
        return _build_result(
            semantic_jobs,
            semantic_jobs,
            "semantic",
            llm_shortlisted_jobs=None,
            gemini_reviewed_jobs=None,
        )

    effective_top_n = min(
        len(jobs),
        max(1, top_n or _safe_int_env("JOB_SCRAPER_LLM_TOP_N", DEFAULT_TOP_N)),
    )
    candidate_jobs = jobs[:effective_top_n]

    effective_batch_size = max(
        1,
        batch_size or _safe_int_env("JOB_SCRAPER_LLM_BATCH_SIZE", DEFAULT_BATCH_SIZE),
    )
    effective_description_chars = max(
        200,
        description_chars
        or _safe_int_env(
            "JOB_SCRAPER_LLM_DESCRIPTION_CHARS",
            DEFAULT_DESCRIPTION_CHARS,
        ),
    )
    effective_model = (
        model
        or os.getenv("JOB_SCRAPER_LLM_MODEL", "").strip()
        or DEFAULT_GEMINI_MODEL
    )
    retry_deadline = time.monotonic() + GEMINI_RETRY_TOTAL_WAIT_SECONDS

    try:
        client = client or _build_client()
    except RuntimeError as exc:
        error_message = str(exc)
        print(f"Warning: Gemini reranking unavailable, not sending digest. {error_message}")
        return _build_result(
            [],
            [],
            "gemini_failed",
            llm_shortlisted_jobs=0,
            gemini_reviewed_jobs=0,
            review_error=error_message,
            review_error_stage="client_setup",
        )

    if client is None:
        return _build_result(
            [],
            [],
            "gemini_failed",
            llm_shortlisted_jobs=0,
            gemini_reviewed_jobs=0,
            review_error="Gemini API key is missing.",
            review_error_stage="client_setup",
        )

    try:
        screened_candidates = _run_batch_screening(
            candidate_jobs,
            recipient_profile,
            client,
            effective_model,
            effective_batch_size,
            effective_description_chars,
            retry_deadline,
        )
    except Exception as exc:
        error_message = str(exc)
        print(
            "Warning: Gemini batch screening failed, not sending digest. "
            f"{error_message}"
        )
        return _build_result(
            [],
            [],
            "gemini_failed",
            llm_shortlisted_jobs=0,
            gemini_reviewed_jobs=0,
            review_error=error_message,
            review_error_stage="batch_screening",
        )

    if not screened_candidates:
        return _build_result(
            [],
            candidate_jobs,
            "gemini",
            llm_shortlisted_jobs=0,
            gemini_reviewed_jobs=len(candidate_jobs),
        )

    try:
        final_shortlist = _run_final_rerank(
            screened_candidates,
            recipient_profile,
            client,
            effective_model,
            retry_deadline,
        )
    except Exception as exc:
        error_message = str(exc)
        print(
            "Warning: Gemini final reranking failed, not sending digest. "
            f"{error_message}"
        )
        return _build_result(
            [],
            [],
            "gemini_failed",
            llm_shortlisted_jobs=0,
            gemini_reviewed_jobs=0,
            review_error=error_message,
            review_error_stage="final_rerank",
        )

    return _build_result(
        _strip_internal_fields(final_shortlist),
        candidate_jobs,
        "gemini",
        llm_shortlisted_jobs=len(final_shortlist),
        gemini_reviewed_jobs=len(candidate_jobs),
    )
