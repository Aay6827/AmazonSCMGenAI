import re

_PII_PATTERNS = [
    ("[REDACTED_EMAIL]", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("[REDACTED_CARD]", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("[REDACTED_PHONE]", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?\d{10}(?!\d)")),
]

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
        r"disregard (the |your )?(system|previous) (prompt|instructions)",
        r"reveal (your |the )?system prompt",
    )
]


def redact(text: str) -> tuple[str, int]:
    """Replace PII with placeholders. Returns (clean_text, number_of_redactions)."""
    total = 0
    for placeholder, pattern in _PII_PATTERNS:
        text, n = pattern.subn(placeholder, text)
        total += n
    return text, total


def is_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)