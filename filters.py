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
    "talent acquisition",
    "recruiter",
    "marketing",
    "partnerships",
    "general counsel",
    "legal counsel",
]

AUTHORIZATION_MISMATCH_PATTERNS = [
    r"authorized to work in (?:the )?(?:us|usa|united states)\b",
    r"eligible to work in (?:the )?(?:us|usa|united states)\b",
    r"must be based in (?:the )?(?:us|usa|united states)\b",
    r"must reside in (?:the )?(?:us|usa|united states)\b",
    r"authorized to work in canada\b",
    r"eligible to work in canada\b",
]
