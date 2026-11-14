"""Table-driven rules for the files people edit: unknown keys (with suggestions) and bad values.

Rules read the loaded model (`Person.extra`, `Event.extra`, ...) and the `site.yml` mapping. None of them raises
on odd input; `check_tree` still guards each call so one broken rule never hides the rest.
"""
from __future__ import annotations

import difflib

from .issues import Issue
from .textvalues import is_extension, parse_bool
from .store import _EVENT_KEYS, _PARTNERSHIP_KEYS, PERSON_KEYS

__all__ = ["is_extension", "suggest", "person_issues"]

PERSON_KNOWN = set(PERSON_KEYS) | {"media"}  # media is reserved: kept and ignored
NAME_KNOWN = {"given", "surname"}
VITAL_KNOWN = {"date", "place", "note", "cite"}
EVENT_KNOWN = set(_EVENT_KEYS)
PARTNERSHIP_KNOWN = set(_PARTNERSHIP_KEYS)


def suggest(key: str, known) -> str | None:
    matches = difflib.get_close_matches(str(key).lower(), sorted(known), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _hint(key: str, known) -> str:
    guess = suggest(key, known)
    return f" (did you mean {guess!r}?)" if guess else ""


def _unknown(keys, known, owner: str, prefix: str, where, out: list[Issue]) -> None:
    for key in keys:
        if key in known or is_extension(str(key)):
            continue
        name = f"{prefix}{key}"
        out.append(Issue("W-UNKNOWN-KEY", f"{owner}unknown key {name!r}{_hint(str(key), known)}", where))


def person_issues(person) -> list[Issue]:
    out: list[Issue] = []
    where, owner = person.location, f"{person.id}: "
    _unknown(person.extra, PERSON_KNOWN, owner, "", where, out)
    _unknown(person.name_extra, NAME_KNOWN, owner, "name.", where, out)
    for label, event in (("birth", person.birth), ("death", person.death)):
        if event is not None:
            _unknown(event.extra, VITAL_KNOWN, owner, f"{label}.", where, out)
    for number, entry in enumerate(person.events, 1):
        _unknown(entry.extra, EVENT_KNOWN, owner, f"events[{number}].", where, out)
    for number, entry in enumerate(person.partnerships, 1):
        _unknown(entry.extra, PARTNERSHIP_KNOWN, owner, f"partnerships[{number}].", where, out)
    text = getattr(person, "living_text", None)
    if text is not None and parse_bool(text) is None:
        out.append(Issue("W-BAD-LIVING", f"{person.id}: living {text!r} is not true or false; it is ignored", where))
    return out
