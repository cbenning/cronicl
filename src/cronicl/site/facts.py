from __future__ import annotations

# How an event or attribute reads when it is about one person ("buried", "worked as Carpenter"). Any slug that is
# not listed is shown as the slug with hyphens as spaces, followed by ": <value>" when there is a value.
_PLAIN = {
    "baptism": "baptised",
    "christening": "christened",
    "confirmation": "confirmed",
    "burial": "buried",
    "cremation": "cremated",
    "immigration": "immigrated",
    "emigration": "emigrated",
    "naturalization": "naturalised",
    "residence": "lived",
    "census": "recorded in a census",
    "graduation": "graduated",
    "retirement": "retired",
    "will": "made a will",
    "probate": "estate went to probate",
    "adoption": "was adopted",
}
_WITH_VALUE = {"occupation": ("worked as", "worked"), "education": ("studied", "studied")}


def _words(kind: str) -> str:
    return kind.replace("-", " ").strip() or "event"


def fact_text(kind: str, value: str | None) -> str:
    if kind in _WITH_VALUE:
        with_value, without = _WITH_VALUE[kind]
        return f"{with_value} {value}" if value else without
    if kind in _PLAIN:
        return _PLAIN[kind]
    words = _words(kind)
    return f"{words}: {value}" if value else words


def fact_label(kind: str) -> str:
    words = _words(kind)
    return words[:1].upper() + words[1:]
