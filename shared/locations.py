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

BAD_LOCATION_KEYWORDS = [
    "hop",
    "warehouse",
    "trading estate",
    "rider",
    "delivery",
    "store",
    "kitchen",
    "site",
]

COUNTRY_LEVEL_UK_PATTERNS = [
    r"\buk\b",
    r"united kingdom",
    r"\bgb\b",
    r"remote\s*\(uk\)",
    r"\bengland\b",
    r"\bscotland\b",
]

FOREIGN_LOCATION_KEYWORDS = [
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

US_STATE_CODES = {
    "ak",
    "al",
    "ar",
    "az",
    "ca",
    "co",
    "ct",
    "dc",
    "de",
    "fl",
    "ga",
    "hi",
    "ia",
    "id",
    "il",
    "in",
    "ks",
    "ky",
    "la",
    "ma",
    "md",
    "me",
    "mi",
    "mn",
    "mo",
    "ms",
    "mt",
    "nc",
    "nd",
    "ne",
    "nh",
    "nj",
    "nm",
    "nv",
    "ny",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "va",
    "vt",
    "wa",
    "wi",
    "wv",
    "wy",
}


def _contains_location_term(location_text, location_term):
    pattern = (
        r"(?<![a-z])"
        + re.escape(location_term).replace(r"\ ", r"\s+")
        + r"(?![a-z])"
    )
    return re.search(pattern, location_text) is not None


def _decision(accepted, reason, location="", matched_term=""):
    return {
        "accepted": accepted,
        "reason": reason,
        "location": location,
        "matched_term": matched_term,
    }


def _contains_us_state_code(location_text):
    state_pattern = "|".join(sorted(US_STATE_CODES))
    return bool(
        re.search(
            rf"(?:^|[,\s(/-])(?:{state_pattern})(?:$|[,\s)/-])",
            location_text,
        )
    )


def get_uk_location_decision(locations):
    if isinstance(locations, str):
        locations = [locations]

    fallback_rejection = _decision(False, "no_match")

    for location in locations:
        if not location:
            continue

        normalized = location.lower()

        bad_keyword = next(
            (keyword for keyword in BAD_LOCATION_KEYWORDS if keyword in normalized),
            "",
        )
        if bad_keyword:
            fallback_rejection = _decision(
                False,
                "bad_keyword",
                location,
                bad_keyword,
            )
            continue

        country_pattern = next(
            (
                pattern
                for pattern in COUNTRY_LEVEL_UK_PATTERNS
                if re.search(pattern, normalized)
            ),
            "",
        )
        if country_pattern:
            return _decision(True, "country_level_uk", location, country_pattern)

        foreign_keyword = next(
            (
                keyword
                for keyword in FOREIGN_LOCATION_KEYWORDS
                if keyword in normalized
            ),
            "",
        )
        if foreign_keyword:
            fallback_rejection = _decision(
                False,
                "foreign_keyword",
                location,
                foreign_keyword,
            )
            continue

        if _contains_us_state_code(normalized):
            fallback_rejection = _decision(
                False,
                "foreign_region",
                location,
                "us_state_code",
            )
            continue

        for location_term in sorted(UK_LOCATION_TERMS):
            if _contains_location_term(normalized, location_term):
                return _decision(
                    True,
                    "uk_location_term",
                    location,
                    location_term,
                )

        fallback_rejection = _decision(False, "no_match", location)

    return fallback_rejection


def is_uk_location(locations):
    return get_uk_location_decision(locations)["accepted"]


def dedupe_keep_order(values):
    return list(dict.fromkeys(value for value in values if value))


def format_locations(locations):
    unique_locations = dedupe_keep_order(locations)
    return ", ".join(unique_locations)
