"""Table-driven rules for the files people edit: unknown keys (with suggestions) and bad values.

Rules read the loaded model (`Person.extra`, `Event.extra`, ...) and the `site.yml` mapping. None of them raises
on odd input; `check_tree` still guards each call so one broken rule never hides the rest.
"""
from __future__ import annotations

import difflib

from .issues import Issue
from .textvalues import is_extension, parse_bool

__all__ = ["is_extension", "suggest"]



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
