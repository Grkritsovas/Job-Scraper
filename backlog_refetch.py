import requests

from shared.descriptions import (
    HEADERS,
    MIN_VISIBLE_TEXT_LENGTH,
    extract_ashby_description_text,
    get_visible_text,
    normalize_text_whitespace,
)


DEAD_STATUS_CODES = {404, 410}
TEMPORARY_STATUS_CODES = {408, 425, 429}


def refetch_backlog_job_description(url, timeout=20):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.Timeout:
        return _result(url, "temporary_failure", reason="timeout")
    except requests.ConnectionError:
        return _result(url, "temporary_failure", reason="connection_error")
    except requests.RequestException as exc:
        return _result(
            url,
            "temporary_failure",
            reason=exc.__class__.__name__,
        )

    status_code = response.status_code
    if status_code in DEAD_STATUS_CODES:
        return _result(
            url,
            "dead",
            status_code=status_code,
            reason="missing_page",
        )
    if status_code in TEMPORARY_STATUS_CODES or status_code >= 500:
        return _result(
            url,
            "temporary_failure",
            status_code=status_code,
            reason="http_status",
        )

    if status_code >= 400:
        return _result(
            url,
            "temporary_failure",
            status_code=status_code,
            reason="http_status",
        )

    description = _extract_description(url, response.text)
    if not description:
        return _result(
            url,
            "unusable",
            status_code=status_code,
            reason="no_usable_text",
        )

    return _result(
        url,
        "ok",
        description=description,
        status_code=status_code,
        reason="description_text",
    )


def _extract_description(url, html):
    if "jobs.ashbyhq.com" in url:
        ashby_description = normalize_text_whitespace(
            extract_ashby_description_text(html)
        )
        if len(ashby_description) >= MIN_VISIBLE_TEXT_LENGTH:
            return ashby_description

    visible_text = normalize_text_whitespace(get_visible_text(html))
    if len(visible_text) >= MIN_VISIBLE_TEXT_LENGTH:
        return visible_text
    return ""


def _result(url, status, description="", status_code=None, reason=""):
    return {
        "url": url,
        "status": status,
        "description": description,
        "status_code": status_code,
        "reason": reason,
    }
