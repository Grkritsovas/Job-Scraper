import re


UK_LOCATION_TERMS = {
    "aberdeen",
    "bath",
    "basingstoke",
    "blackburn",
    "blackpool",
    "birmingham",
    "bournemooth",
    "bournemouth",
    "bristol",
    "cambridge",
    "cardif",
    "cardiff",
    "cheltenham",
    "coventry",
    "crawley",
    "crawly",
    "darlington",
    "devon",
    "doncaster",
    "dorchester",
    "dumfries",
    "edinburgh",
    "edingburgh",
    "exeter",
    "falkirk",
    "farnborough",
    "farnham",
    "galashiels",
    "glasgow",
    "guildford",
    "harrow",
    "hinckley",
    "horsham",
    "hull",
    "inverness",
    "isle of wight",
    "kent",
    "kilmarnock",
    "kingston upon thames",
    "lancashire",
    "lancaster",
    "leeds",
    "leicester",
    "london",
    "maidstone",
    "manchester",
    "middlesborough",
    "middlesbrough",
    "newcastle",
    "newport",
    "oldham",
    "oxford",
    "oxfordshire",
    "perth",
    "plymouth",
    "portsmouth",
    "reading",
    "redhill",
    "scotland",
    "sheffield",
    "shefield",
    "slough",
    "somerset",
    "southampton",
    "stockport",
    "stockton-on-tees",
    "surrey",
    "swindon",
    "taunton",
    "teesside",
    "torquay",
    "truro",
    "warwick",
    "west midlands",
    "weybridge",
    "woking",
    "york",
}


def _contains_location_term(location_text, location_term):
    pattern = (
        r"(?<![a-z])"
        + re.escape(location_term).replace(r"\ ", r"\s+")
        + r"(?![a-z])"
    )
    return re.search(pattern, location_text) is not None


def is_uk_location(locations):
    if isinstance(locations, str):
        locations = [locations]

    bad_keywords = [
        "hop",
        "warehouse",
        "trading estate",
        "rider",
        "delivery",
        "store",
        "kitchen",
        "site",
    ]

    country_level_uk_patterns = [
        r"\buk\b",
        r"united kingdom",
        r"\bgb\b",
        r"remote\s*\(uk\)",
        r"\bengland\b",
        r"\bscotland\b",
    ]

    foreign_keywords = [
        "united states",
        "usa",
        "canada",
        "australia",
        "ukraine",
        "brazil",
        "mexico",
        "new york",
        "serbia",
        "germany",
        "romania",
        "cyprus",
        "switzerland",
        "portugal",
        "lithuania",
        "czech republic",
        "poland",
        "spain",
        "france",
        "italy",
        "ireland",
        "belgrade",
        "berlin",
        "sydney",
        "new south wales",
    ]

    for location in locations:
        if not location:
            continue

        normalized = location.lower()

        if any(keyword in normalized for keyword in bad_keywords):
            continue

        if any(re.search(pattern, normalized) for pattern in country_level_uk_patterns):
            return True

        if any(keyword in normalized for keyword in foreign_keywords):
            continue

        if any(
            _contains_location_term(normalized, location_term)
            for location_term in UK_LOCATION_TERMS
        ):
            return True

    return False


def dedupe_keep_order(values):
    return list(dict.fromkeys(value for value in values if value))


def format_locations(locations):
    unique_locations = dedupe_keep_order(locations)
    return ", ".join(unique_locations)
