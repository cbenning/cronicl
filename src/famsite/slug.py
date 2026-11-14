from __future__ import annotations

import re
import unicodedata

MAX_ID_LEN = 64
FALLBACK_SLUG = "person"

_VALID_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SPECIAL = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l", "þ": "th"}


def fold_slug(text: str) -> str:
    """Fold to lowercase ASCII words joined by single hyphens, with no length limit."""
    lowered = text.lower()
    for char, replacement in _SPECIAL.items():
        lowered = lowered.replace(char, replacement)
    folded = unicodedata.normalize("NFKD", lowered)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def slugify(text: str) -> str:
    """Fold to lowercase ASCII words joined by single hyphens, at most MAX_ID_LEN long."""
    return fold_slug(text)[:MAX_ID_LEN].strip("-")


def person_slug(given: str | None, surname: str | None) -> str:
    parts = [slugify(part) for part in (surname, given) if part]
    joined = "-".join(part for part in parts if part)[:MAX_ID_LEN].strip("-")
    return joined or FALLBACK_SLUG


def is_valid_id(value: str | None) -> bool:
    return bool(value) and len(value) <= MAX_ID_LEN and bool(_VALID_ID.match(value))


def unique_id(base: str, taken: set[str]) -> str:
    candidate = base
    counter = 2
    while candidate in taken:
        suffix = f"-{counter}"
        candidate = base[: MAX_ID_LEN - len(suffix)].rstrip("-") + suffix
        counter += 1
    return candidate


def natural_key(text: str) -> list:
    """Sort key that orders embedded numbers numerically: I2 < I10."""
    return [int(token) if token.isdigit() else token for token in re.split(r"(\d+)", text)]
