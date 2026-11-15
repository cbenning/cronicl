"""Rules for the records of `family.yml`: unknown keys, blanks, dates, and the once-only / placement conventions.

They read each record as loaded (`Person.raw`, a yamltext.Mapping that knows its lines), so every issue can name the
exact line.
"""
from __future__ import annotations

import difflib
import re

from .dates import is_unknown, parse_between, parse_date, parse_span, plain_form, runs_backwards
from .issues import Issue
from .textvalues import is_extension, normal_type, parse_bool
from .validate import suggest
from .yamltext import Mapping, Sequence

PERSON_KNOWN = {"name", "sex", "birth", "death", "parents", "events", "portrait", "living", "refs", "bio"}
NAME_KNOWN = {"given", "surname", "prefix", "suffix", "nickname", "also"}
VITAL_KNOWN = {"date", "place", "note", "cite"}
EVENT_KNOWN = {"type", "date", "place", "value", "note", "cite"}
REFS_KNOWN = {"gedcom", "gallery"}
COUPLE_KNOWN = {"events", "note"}
SEX_WORDS = ("male", "female", "unknown", "other")
COUPLE_ONLY = ("marriage", "divorce", "engagement", "civil-union", "partnership", "separation", "annulment", "end")
ONCE_ONLY = ("burial", "cremation")
_ALIASES = {"wedding": "marriage", "married": "marriage", "wed": "marriage", "marry": "marriage", "divorced": "divorce", "annulled": "annulment",
            "separated": "separation", "engaged": "engagement", "union": "civil-union"}


def type_guess(kind: str) -> str | None:
    """The couple event type a near-miss most likely meant, or None when it looks like some other event."""
    if kind in _ALIASES:
        return _ALIASES[kind]
    matches = difflib.get_close_matches(kind, COUPLE_ONLY, n=1, cutoff=0.75)
    return matches[0] if matches else None


def _hint(key: str, known) -> str:
    guess = suggest(key, known)
    return f" (did you mean {guess!r}?)" if guess else ""


def _keys(mapping: Mapping, known: set, prefix: str, owner: str, source: str, out: list[Issue]) -> None:
    """Unknown keys (with suggestions) and blank values in one mapping."""
    one_line = len(mapping) > 1 and len(set(mapping.lines.values())) == 1  # a `{a: 1, b: 2}` written on one line
    for key, value in mapping.items():
        if is_extension(str(key)):
            continue
        line = mapping.lines.get(key)
        if key not in known:
            if value == "" and one_line:
                out.append(
                    Issue(
                        "W-FLOW-COMMA",
                        f"{owner}{prefix}{key}: {key!r} looks like the end of text that contains a comma; "
                        "quote the text, e.g. place: \"London, England\"",
                        source,
                        line,
                    )
                )
            else:
                out.append(Issue("W-UNKNOWN-KEY", f"{owner}unknown key {prefix + str(key)!r}{_hint(str(key), known)}", source, line))
        elif value == "":
            out.append(Issue("W-BLANK", f"{owner}{prefix}{key} is blank; give it a value or remove it", source, line))


def _shape(mapping: Mapping, keys, prefix: str, owner: str, source: str, out: list[Issue], *, lists_ok=()) -> None:
    """Text expected, a list or mapping typed: report it (the reader would otherwise ignore it without a word)."""
    for key in keys:
        value = mapping.get(key)
        line = mapping.lines.get(key)
        if isinstance(value, Mapping):
            out.append(Issue("E-RECORD-SHAPE", f"{owner}{prefix}{key} must be text, not a mapping", source, line))
        elif isinstance(value, Sequence):
            if key not in lists_ok:
                out.append(Issue("E-RECORD-SHAPE", f"{owner}{prefix}{key} must be text, not a list", source, line))
            elif any(not isinstance(item, str) for item in value):
                out.append(Issue("E-RECORD-SHAPE", f"{owner}{prefix}{key} must be text or a list of text", source, line))


def _date(text, label: str, line, owner: str, source: str, out: list[Issue], *, once: bool = False, spans_ok: bool = True) -> None:
    if not isinstance(text, str) or not text.strip() or is_unknown(text):
        return
    if parse_span(text) is not None:
        if not spans_ok:
            out.append(Issue("W-DATE-SPAN", f"{owner}{label}: a span ({text!r}) is for things that last; give one date", source, line))
            return
        first, last = parse_span(text)
        a, b = plain_form(first), plain_form(last)
        if a and b and runs_backwards(a, b):
            out.append(Issue("W-END-BEFORE-START", f"{owner}{label} ends ({last}) before it starts ({first})", source, line))
        return
    parsed = parse_date(text)
    between = parse_between(text)
    if between is not None and runs_backwards(*between):
        out.append(Issue("W-END-BEFORE-START", f"{owner}{label} runs backwards ({text!r}): the second date is before the first", source, line))
        return
    if parsed is None:
        extra = "; it does not count as a death, so the person is treated as living (write `unknown` if they died)" if label == "death" else ""
        out.append(Issue("W-DATE-UNPARSED", f"{owner}{label} date {text!r} is not a recognised date{extra}", source, line))


def _events(entries, owner: str, source: str, out: list[Issue], *, couple: bool) -> None:
    if not isinstance(entries, Sequence):
        return
    seen: dict[str, int] = {}
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, Mapping):
            continue
        line = entries.lines[number - 1]
        _keys(entry, EVENT_KNOWN, f"events[{number}].", owner, source, out)
        _shape(entry, ("type", "date", "place", "value", "note", "cite"), f"events[{number}].", owner, source, out, lists_ok=("cite",))
        kind = normal_type(entry.get("type"))
        label = kind or "event"
        if couple and kind and kind not in COUPLE_ONLY:
            guess = type_guess(kind)
            if guess:
                out.append(Issue("W-COUPLE-EVENT-TYPE", f"{owner}events[{number}] type {kind!r} is kept as written; did you mean {guess!r}?", source, line))
        if not kind:
            out.append(Issue("W-EVENT-NO-TYPE", f"{owner}events[{number}] has no type", source, line))
        spans_ok = not (couple and kind in ("marriage", "divorce"))
        _date(entry.get("date"), label, entry.lines.get("date", line), owner, source, out, spans_ok=spans_ok)
        if not couple:
            if kind in ("birth", "death"):
                out.append(Issue("W-EVENT-IS-FIELD", f"{owner}events[{number}] is a {kind}: use the `{kind}:` field instead", source, line))
            elif kind in COUPLE_ONLY:
                out.append(
                    Issue("W-EVENT-PLACEMENT", f"{owner}events[{number}] ({kind}) is about a couple: write it in the couple's record", source, line)
                )
            if kind in ONCE_ONLY:
                seen[kind] = seen.get(kind, 0) + 1
                if seen[kind] > 1:
                    out.append(Issue("W-EVENT-ONCE", f"{owner}more than one {kind}: a person has one", source, line))


def family_person_issues(person) -> list[Issue]:
    """Everything the file-level rules say about one person's record and about the couple records filed under them."""
    out: list[Issue] = []
    raw, source = person.raw, person.source
    if isinstance(raw, Mapping):
        owner = f"{person.id}: "
        _keys(raw, PERSON_KNOWN, "", owner, source, out)
        _shape(raw, ("sex", "portrait", "bio", "living"), "", owner, source, out)
        name = raw.get("name")
        if isinstance(name, Mapping):
            _keys(name, NAME_KNOWN, "name.", owner, source, out)
            _shape(name, ("given", "surname", "prefix", "suffix", "nickname", "also"), "name.", owner, source, out, lists_ok=("also",))
        for key in ("birth", "death"):
            value = raw.get(key)
            if isinstance(value, Mapping):
                _keys(value, VITAL_KNOWN, f"{key}.", owner, source, out)
                _shape(value, ("date", "place", "note", "cite"), f"{key}.", owner, source, out, lists_ok=("cite",))
                _date(value.get("date"), key, value.lines.get("date"), owner, source, out, spans_ok=False)
            elif isinstance(value, str):
                _date(value, key, raw.lines.get(key), owner, source, out, spans_ok=False)
        refs = raw.get("refs")
        if isinstance(refs, Mapping):
            _keys(refs, REFS_KNOWN, "refs.", owner, source, out)
            _shape(refs, ("gedcom", "gallery"), "refs.", owner, source, out)
        elif isinstance(refs, Sequence) or (isinstance(refs, str) and refs.strip()):
            out.append(Issue("E-RECORD-SHAPE", f"{owner}refs must be a mapping (gedcom, gallery)", source, raw.lines.get("refs")))
        _events(raw.get("events"), owner, source, out, couple=False)
        sex = raw.get("sex")
        if isinstance(sex, str) and sex.strip() and sex.strip().casefold() not in SEX_WORDS:
            out.append(Issue("W-BAD-SEX", f"{owner}sex {sex.strip()!r} is not one of {', '.join(SEX_WORDS)}", source, raw.lines.get("sex")))
        living = raw.get("living")
        if isinstance(living, str) and living != "" and parse_bool(living) is not True:
            hint = "use `death: unknown` for someone who has died" if parse_bool(living) is False else "write `living: true`, or leave it out"
            out.append(Issue("W-LIVING-FALSE", f"{owner}living {living.strip()!r}: {hint}", source, raw.lines.get("living")))
        death = raw.get("death")
        if isinstance(death, Mapping) and not any(isinstance(death.get(k), str) and death.get(k).strip() for k in ("date", "place")):
            out.append(Issue("W-DEATH-EMPTY", f"{owner}death has no date or place, so it does not count as a death; write `date: unknown` if they died", source, raw.lines.get("death")))
        if parse_bool(living) is True and ((isinstance(death, str) and death.strip()) or (isinstance(death, Mapping) and len(death))):
            out.append(Issue("W-LIVING-AND-DEATH", f"{owner}living: true and a death are both given; the person is treated as living", source, raw.lines.get("living")))
        parents = raw.get("parents")
        if isinstance(parents, Sequence):
            ids = [p.strip() for p in parents if isinstance(p, str)]
            if len(ids) != len(set(ids)):
                out.append(Issue("W-DUPLICATE-PARENT", f"{owner}the same parent is listed twice", source, raw.lines.get("parents")))
    for other, record, couple_source, line in getattr(person, "couple_records", []):
        owner = f"{person.id} + {other}: "
        if isinstance(record, Mapping):
            _keys(record, COUPLE_KNOWN, "", owner, couple_source, out)
            _shape(record, ("note",), "", owner, couple_source, out)
            _events(record.get("events"), owner, couple_source, out, couple=True)
    return out
