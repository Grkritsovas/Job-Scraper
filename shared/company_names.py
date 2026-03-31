from urllib.parse import urlparse


def normalize_company_name(value):
    cleaned = value.replace(".com", "").replace(".io", "")
    cleaned = cleaned.replace("-", " ").replace(".", " ").strip()
    return " ".join(part.capitalize() for part in cleaned.split()) or value


def get_company_name_from_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    host = host.split(":", 1)[0]
    host_parts = host.split(".")
    label = host_parts[0]

    if label in {"careers", "jobs", "apply", "work", "join"} and len(host_parts) > 1:
        label = host_parts[1]

    return normalize_company_name(label)
