"""Table-driven rules for the files people edit: unknown keys (with suggestions) and bad values.

Rules read the loaded model (`Person.extra`, `Event.extra`, ...) and the `site.yml` mapping. None of them raises
on odd input; `check_tree` still guards each call so one broken rule never hides the rest.
"""
from __future__ import annotations

import difflib

from .issues import Issue
from .settings import is_extension, parse_bool, parse_int, privacy_settings
from .store import _EVENT_KEYS, _PARTNERSHIP_KEYS, PERSON_KEYS

__all__ = ["is_extension", "suggest", "person_issues", "site_issues"]

PERSON_KNOWN = set(PERSON_KEYS) | {"media"}  # media is reserved: kept and ignored
NAME_KNOWN = {"given", "surname"}
VITAL_KNOWN = {"date", "place", "note", "cite"}
EVENT_KNOWN = set(_EVENT_KEYS)
PARTNERSHIP_KNOWN = set(_PARTNERSHIP_KEYS)
SITE_KNOWN = {"title", "intro", "home", "edit_url", "contact", "schema_version", "privacy", "place_groups", "gallery"}
PRIVACY_KNOWN = {"living", "cutoff_years", "id_salt"}
SITE_TEXT_KEYS = ("title", "intro", "home", "edit_url", "contact")


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


def _is_collection(value) -> bool:
    return isinstance(value, (list, dict))


def site_issues(site: dict, people: dict) -> list[Issue]:
    out: list[Issue] = []
    if not isinstance(site, dict) or site.get("_unreadable"):
        return out
    path = "site.yml"
    _unknown([k for k in site if isinstance(k, str)], SITE_KNOWN, "", "", path, out)
    for key in SITE_TEXT_KEYS:
        if key in site and _is_collection(site[key]):
            out.append(Issue("W-SITE-VALUE", f"{key} must be text; it is ignored", path))
    if "place_groups" in site:
        groups = site["place_groups"]
        if not isinstance(groups, dict):
            out.append(Issue("W-SITE-VALUE", "place_groups must be a mapping of region: country; it is ignored", path))
        else:
            for key, value in groups.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    out.append(Issue("W-PLACE-GROUPS", f"place_groups entry {str(key)!r} must be text: text; it is ignored", path))
    if "privacy" in site:
        block = site["privacy"]
        if not isinstance(block, dict):
            out.append(Issue("E-PRIVACY-MODE", "privacy must be a mapping such as `living: placeholder`; living people are treated as placeholders", path))
        else:
            _unknown(list(block), PRIVACY_KNOWN, "", "privacy.", path, out)
            if "living" in block:
                setting = privacy_settings({"privacy": {"living": block["living"]}})
                if setting.broken:
                    out.append(Issue("E-PRIVACY-MODE", f"privacy.living {block['living']!r} is not full, placeholder or hidden; living people are treated as placeholders", path))
            if _is_collection(block.get("id_salt")):
                out.append(Issue("E-PRIVACY-SALT", "privacy.id_salt must be text; an empty salt makes anonymised ids guessable", path))
            if "cutoff_years" in block and parse_int(block["cutoff_years"]) is None:
                out.append(Issue("W-PRIVACY-CUTOFF", f"privacy.cutoff_years {block['cutoff_years']!r} is not a whole number of at least 1; 100 is used", path))
    settings = privacy_settings(site)
    if settings.living != "full" and not settings.salt and "privacy" in site and isinstance(site["privacy"], dict) and not _is_collection(site["privacy"].get("id_salt")):
        out.append(Issue("W-PRIVACY-NO-SALT", "privacy.id_salt is empty: anonymised ids of living people can be guessed from their real ids", path))
    return out
