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

HARD_ELIGIBILITY_TITLE_TERMS = [
    "intern",
    "internship",
]

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
    r"\bmust be enrolled in\b",
    r"\bstudents only\b",
    r"\bcurrent student\b",
]
