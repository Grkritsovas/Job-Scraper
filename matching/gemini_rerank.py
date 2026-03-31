import json
import os

from matching.profile_library import build_profile_specs
from shared.descriptions import normalize_text_whitespace, strip_matching_boilerplate


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_TOP_N = 100
DEFAULT_BATCH_SIZE = 10
DEFAULT_DESCRIPTION_CHARS = 1600
FALSEY_ENV_VALUES = {"", "0", "false", "no", "off"}
RESPONSE_JSON_SCHEMA = {
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
    raw_value = os.getenv("JOB_SCRAPER_LLM_RERANK_ENABLED")
    if raw_value is None:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    return raw_value.strip().lower() not in FALSEY_ENV_VALUES


def _safe_int_env(name, default):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        return int(raw_value)
    except ValueError:
        return default


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
    return {
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


def _build_prompt(recipient_profile, jobs, description_chars):
    profiles = [
        {
            "label": spec["label"],
            "text": normalize_text_whitespace(spec["text"]),
        }
        for spec in build_profile_specs(recipient_profile)
    ]
    negative_profile_texts = [
        normalize_text_whitespace(text)
        for text in recipient_profile.get("negative_profile_texts", [])
        if normalize_text_whitespace(text)
    ]
    candidate_payload = {
        "instructions": {
            "primary_source_of_truth": (
                "The target profiles are the main decision rule. "
                "Only shortlist jobs that clearly fit at least one target profile."
            ),
            "cv_usage": (
                "The CV summary is supporting context only. "
                "Use it to judge transferable evidence, not to override the target profiles."
            ),
            "selection_rule": (
                "Be strict. Do not shortlist roles just because they sound broadly "
                "technical, analytical, or corporate."
            ),
            "level_preference": (
                "Prefer junior, graduate, grad, and entry-level roles. "
                "Be cautious with manager, lead, senior, and staff roles."
            ),
            "output_rule": (
                "Return only shortlisted jobs. If none should be kept, return an empty list. "
                "For why_apply, write at most 2 short simple sentences."
            ),
        },
        "candidate": {
            "target_profiles": profiles,
            "cv_summary": normalize_text_whitespace(recipient_profile.get("cv_summary", "")),
            "negative_profile_texts": negative_profile_texts,
        },
        "jobs": [
            _build_job_payload(job, description_chars)
            for job in jobs
        ],
    }
    return (
        "Rerank these jobs for one candidate. "
        "Return only the shortlisted jobs as JSON matching the schema.\n\n"
        f"{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}"
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


def _parse_shortlisted_jobs(response_text):
    payload = json.loads(response_text or "{}")
    shortlisted_jobs = payload.get("shortlisted_jobs")
    if isinstance(shortlisted_jobs, list):
        return shortlisted_jobs
    return []


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
        return []

    effective_top_n = min(
        len(jobs),
        max(1, top_n or _safe_int_env("JOB_SCRAPER_LLM_TOP_N", DEFAULT_TOP_N)),
    )
    candidate_jobs = jobs[:effective_top_n]
    if not gemini_rerank_enabled():
        return candidate_jobs

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

    try:
        client = client or _build_client()
    except RuntimeError as exc:
        print(f"Warning: {exc}")
        return candidate_jobs

    if client is None:
        return candidate_jobs

    original_indexes = {
        job["url"]: index
        for index, job in enumerate(candidate_jobs)
        if job.get("url")
    }
    shortlisted_jobs = []
    seen_urls = set()

    try:
        for batch in _chunked(candidate_jobs, effective_batch_size):
            batch_by_url = {
                job["url"]: job
                for job in batch
                if job.get("url")
            }
            prompt = _build_prompt(
                recipient_profile,
                batch,
                effective_description_chars,
            )
            response = client.models.generate_content(
                model=effective_model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": RESPONSE_JSON_SCHEMA,
                },
            )
            for item in _parse_shortlisted_jobs(getattr(response, "text", "")):
                job_url = normalize_text_whitespace(item.get("job_url", ""))
                if not job_url or job_url in seen_urls or job_url not in batch_by_url:
                    continue

                try:
                    fit_score = int(item.get("fit_score", 0))
                except (TypeError, ValueError):
                    fit_score = 0
                fit_score = max(0, min(100, fit_score))
                why_apply = normalize_text_whitespace(item.get("why_apply", ""))

                original_job = batch_by_url[job_url]
                shortlisted_jobs.append(
                    {
                        **original_job,
                        "semantic_ranking_score": original_job.get("ranking_score"),
                        "ranking_score": fit_score / 100.0,
                        "llm_fit_score": fit_score,
                        "why_apply": why_apply,
                    }
                )
                seen_urls.add(job_url)
    except Exception as exc:
        print(f"Warning: Gemini reranking failed, using semantic shortlist instead. {exc}")
        return candidate_jobs

    shortlisted_jobs.sort(
        key=lambda job: (
            -job.get("llm_fit_score", 0),
            original_indexes.get(job.get("url"), 10**9),
        )
    )
    return shortlisted_jobs
