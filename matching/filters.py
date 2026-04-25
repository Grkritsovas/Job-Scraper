HARD_SENIORITY_TERMS = [
    "senior",
    "staff",
    "lead",
    "principal",
    "head",
    "director",
]

HARD_COMMERCIAL_TERMS = [
    "sales",
    "account executive",
    "business development",
    "customer success",
    "designer",
    "talent acquisition",
    "talent community",
    "recruiter",
    "marketing",
    "partnerships",
    "general counsel",
    "legal counsel",
]

RECIPIENT_AWARE_COMMERCIAL_TERMS = {
    "marketing",
}

HARD_ELIGIBILITY_TITLE_TERMS = []

AUTHORIZATION_MISMATCH_PATTERNS = [
    r"authorized to work in (?:the )?(?:us|usa|united states)\b",
    r"eligible to work in (?:the )?(?:us|usa|united states)\b",
    r"must be based in (?:the )?(?:us|usa|united states)\b",
    r"must reside in (?:the )?(?:us|usa|united states)\b",
    r"authorized to work in canada\b",
    r"eligible to work in canada\b",
]

ELIGIBILITY_REJECT_PATTERNS = [
    r"\bmust be planning on graduating in \d{4}\b",
    r"\bthis should be your final internship before graduating\b",
    r"\bmust be (?:currently )?enrolled\b",
    r"\bcurrently enrolled\b",
    r"\benrolled in (?:a |an |your )?(?:degree|university|college|school|course|program|programme)\b",
    r"\bpursuing (?:a |an |your )?(?:degree|bachelor|bachelors|master|masters|phd)\b",
    r"\breturning to (?:a |an |your )?(?:degree|university|college|school|course|program|programme)\b",
    r"\breturn to (?:a |an |your )?(?:degree|university|college|school|course|program|programme)\b",
    r"\bstudents only\b",
    r"\bcurrent student\b",
]
