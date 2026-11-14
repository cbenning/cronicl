"""Rules for the records of `family.yml`: unknown keys, blanks, dates, and the once-only / placement conventions.

They read each record as loaded (`Person.raw`, a yamltext.Mapping that knows its lines), so every issue can name the
exact line.
"""
from __future__ import annotations

from .dates import is_unknown, parse_date, parse_span, plain_form
from .issues import Issue
from .textvalues import is_extension, parse_bool
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


def _date(text, label: str, line, owner: str, source: str, out: list[Issue], *, once: bool = False, spans_ok: bool = True) -> None:
    if not isinstance(text, str) or not text.strip() or is_unknown(text):
        return
    if parse_span(text) is not None:
        if not spans_ok:
            out.append(Issue("W-DATE-SPAN", f"{owner}{label}: a span ({text!r}) is for things that last; give one date", source, line))
            return
        first, last = parse_span(text)
        a, b = plain_form(first), plain_form(last)
        if a and b and b < a:
            out.append(Issue("W-END-BEFORE-START", f"{owner}{label} ends ({last}) before it starts ({first})", source, line))
        return
    if parse_date(text) is None:
        out.append(Issue("W-DATE-UNPARSED", f"{owner}{label} date {text!r} is not a recognised date", source, line))


def _events(entries, owner: str, source: str, out: list[Issue], *, couple: bool) -> None:
    if not isinstance(entries, Sequence):
        return
    seen: dict[str, int] = {}
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, Mapping):
            continue
        line = entries.lines[number - 1]
        _keys(entry, EVENT_KNOWN, f"events[{number}].", owner, source, out)
        kind = entry.get("type") if isinstance(entry.get("type"), str) else ""
        kind = kind.strip()
        label = kind or "event"
        if not kind and not couple:
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
        name = raw.get("name")
        if isinstance(name, Mapping):
            _keys(name, NAME_KNOWN, "name.", owner, source, out)
        for key in ("birth", "death"):
            value = raw.get(key)
            if isinstance(value, Mapping):
                _keys(value, VITAL_KNOWN, f"{key}.", owner, source, out)
                _date(value.get("date"), key, value.lines.get("date"), owner, source, out, spans_ok=False)
            elif isinstance(value, str):
                _date(value, key, raw.lines.get(key), owner, source, out, spans_ok=False)
        refs = raw.get("refs")
        if isinstance(refs, Mapping):
            _keys(refs, REFS_KNOWN, "refs.", owner, source, out)
        _events(raw.get("events"), owner, source, out, couple=False)
        sex = raw.get("sex")
        if isinstance(sex, str) and sex.strip() and sex.strip() not in SEX_WORDS:
            out.append(Issue("W-BAD-SEX", f"{owner}sex {sex.strip()!r} is not one of {', '.join(SEX_WORDS)}", source, raw.lines.get("sex")))
        living = raw.get("living")
        if isinstance(living, str) and living != "" and parse_bool(living) is not True:
            hint = "use `death: unknown` for someone who has died" if parse_bool(living) is False else "write `living: true`, or leave it out"
            out.append(Issue("W-LIVING-FALSE", f"{owner}living {living.strip()!r}: {hint}", source, raw.lines.get("living")))
    for other, record, couple_source, line in getattr(person, "couple_records", []):
        owner = f"{person.id} + {other}: "
        if isinstance(record, Mapping):
            _keys(record, COUPLE_KNOWN, "", owner, couple_source, out)
            _events(record.get("events"), owner, couple_source, out, couple=True)
    return out
