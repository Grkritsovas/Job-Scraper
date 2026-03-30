import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAM_NAMES = {
    "_ga",
    "_gl",
    "fbclid",
    "gclid",
    "gbraid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "wbraid",
}
TRACKING_PARAM_PREFIXES = ("utm_",)

KNOWN_PLATFORM_HOSTS = {
    "ashby": {"jobs.ashbyhq.com"},
    "greenhouse": {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    },
    "lever": {"jobs.lever.co"},
}


def normalize_seed_url(url):
    return _sanitize_url(url)


def sanitize_job_url(url, source, target_value=""):
    allowed_hosts = get_allowed_job_hosts(source, target_value)
    if not allowed_hosts:
        return ""

    return _sanitize_url(url, allowed_hosts=allowed_hosts)


def get_allowed_job_hosts(source, target_value=""):
    if source == "nextjs":
        hosts = set()
        for platform_hosts in KNOWN_PLATFORM_HOSTS.values():
            hosts.update(platform_hosts)
        hosts.update(_get_nextjs_target_host_variants(target_value))
        return hosts

    return set(KNOWN_PLATFORM_HOSTS.get(source, set()))


def _get_nextjs_target_host_variants(target_url):
    normalized_target_url = normalize_seed_url(target_url)
    if not normalized_target_url:
        return set()

    parsed = urlsplit(normalized_target_url)
    host = _normalize_host(parsed)
    if not host:
        return set()

    if host.startswith("www."):
        return {host, host[4:]}

    return {host, f"www.{host}"}


def _sanitize_url(url, allowed_hosts=None):
    if not isinstance(url, str):
        return ""

    candidate = url.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return ""

    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return ""

    if parsed.username or parsed.password:
        return ""

    host = _normalize_host(parsed)
    if not host:
        return ""

    if allowed_hosts is not None and host not in allowed_hosts:
        return ""

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    query = _strip_tracking_params(parsed.query)

    return urlunsplit(("https", host, path, query, ""))


def _normalize_host(parsed_url):
    host = (parsed_url.hostname or "").lower().rstrip(".")
    if not host:
        return ""

    port = parsed_url.port
    if port and port not in {80, 443}:
        return ""

    return host


def _strip_tracking_params(query_string):
    if not query_string:
        return ""

    kept_params = []
    for name, value in parse_qsl(query_string, keep_blank_values=True):
        lowered = name.lower()
        if lowered in TRACKING_PARAM_NAMES:
            continue
        if any(lowered.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES):
            continue
        kept_params.append((name, value))

    return urlencode(kept_params, doseq=True)
