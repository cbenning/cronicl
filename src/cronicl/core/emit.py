"""Writing family.yml text: one canonical, tidy layout for people and couples.

Everything here returns text. Values are quoted only when YAML needs it, so what is written reads back as exactly the
same text through `yamltext.load_text`.
"""
from __future__ import annotations

import re

from .dates import parse_span

_PLAIN_SAFE = re.compile(r"^[^\s\-?:,\[\]{}#&*!|>'\"%@`][^\n]*$")
_NEEDS_QUOTES = re.compile(r"(: |:$| #|[,\[\]{}]|\t|^\s|\s$|[\x00-\x1f\x7f  ﻿])")
_LONG = 100


def quote(text: str, *, flow: bool = True) -> str:
    """A scalar safe to write in a flow mapping or list (flow=True) or after `key: ` in a block (flow=False)."""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if text == "":
        return '""'
    needs = bool(_NEEDS_QUOTES.search(text)) if flow else bool(re.search(r"(: |:$| #|\t|^\s|\s$|[\x00-\x1f\x7f  ﻿])", text))
    if not needs and re.match(r"^[\-?:]($|\s)", text):
        needs = True
    if not needs and not _PLAIN_SAFE.match(text) and not re.match(r"^-\S", text):
        needs = True
    if not needs:
        return text
    out = ['"']
    for char in text:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif code < 0x20 or code == 0x7F or char in "  ﻿":
            out.append(f"\\u{code:04x}" if code > 0xFF else f"\\x{code:02x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _flow(pairs: list[tuple[str, str]]) -> str:
    return "{" + ", ".join(f"{key}: {value}" for key, value in pairs) + "}"


def _fact(date=None, place=None, note=None, cite=None, extra=None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if date:
        pairs.append(("date", quote(date)))
    if place:
        pairs.append(("place", quote(place)))
    if note:
        pairs.append(("note", quote(note)))
    cites = [cite] if isinstance(cite, str) else list(cite or [])
    if cites:
        pairs.append(("cite", quote(cites[0]) if len(cites) == 1 else "[" + ", ".join(quote(c) for c in cites) + "]"))
    for key, value in (extra or {}).items():
        pairs.append((key, _any(value)))
    return pairs


def _any(value) -> str:
    """A value of any shape the model may carry in its extras, as flow YAML."""
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{quote(str(k))}: {_any(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_any(v) for v in value) + "]"
    return quote(str(value))


def _line(indent: str, key: str, pairs: list[tuple[str, str]], only_date: bool = False) -> list[str]:
    """`key: {a: 1, b: 2}` on one line, or as a block when it would be long; a lone date is written bare."""
    if only_date and len(pairs) == 1 and pairs[0][0] == "date":
        return [f"{indent}{key}: {pairs[0][1]}"]
    one = f"{indent}{key}: {_flow(pairs)}"
    if len(one) <= _LONG:
        return [one]
    return [f"{indent}{key}:"] + [f"{indent}  {k}: {v}" for k, v in pairs]


def _bio(text: str, indent: str = "  ") -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text:
        return []
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f  ﻿]", text) or any(line.endswith((" ", "\t")) for line in text.split("\n")):
        return [f"{indent}bio: {quote(text)}"]
    head = "|" + ("2" if text[0] in " \t" else "")
    return [f"{indent}bio: {head}"] + [f"{indent}  {line}" if line else "" for line in text.split("\n")]


def event_pairs(entry: dict) -> list[tuple[str, str]]:
    """An events entry (type, date | start/end, place, value, note, cite, extras) as ordered key/value text."""
    pairs = [("type", quote(entry.get("type") or ""))]
    date = entry.get("date")
    if not date and (entry.get("start") or entry.get("end")):
        start, end = entry.get("start"), entry.get("end")
        date = f"FROM {start} TO {end}" if start and end else (f"FROM {start}" if start else f"TO {end}")
    if date:
        pairs.append(("date", quote(date)))
    for key in ("place", "value", "note"):
        if entry.get(key):
            pairs.append((key, quote(entry[key])))
    cites = entry.get("cite")
    cites = [cites] if isinstance(cites, str) else list(cites or [])
    if cites:
        pairs.append(("cite", quote(cites[0]) if len(cites) == 1 else "[" + ", ".join(quote(c) for c in cites) + "]"))
    for key, value in (entry.get("extra") or {}).items():
        pairs.append((key, _any(value)))
    return pairs


def _events(entries: list[dict], indent: str = "  ") -> list[str]:
    if not entries:
        return []
    out = [f"{indent}events:"]
    for entry in entries:
        pairs = event_pairs(entry)
        one = f"{indent}  - {_flow(pairs)}"
        if len(one) <= _LONG + 20:
            out.append(one)
        else:
            out.append(f"{indent}  - {pairs[0][0]}: {pairs[0][1]}")
            out += [f"{indent}    {k}: {v}" for k, v in pairs[1:]]
    return out


def person(pid: str, spec: dict) -> str:
    """One person record. `spec` keys: name{given,surname,prefix,suffix,nickname,also,extra}, sex (a word), birth/death
    (a date string or {date, place, note, cite, extra}), parents, events, portrait, living (True), refs{gedcom,gallery},
    x{key: value} extras, bio."""
    lines = [f"{pid}:"]
    name = spec.get("name") or {}
    pairs = [(k, quote(name[k])) for k in ("given", "surname", "prefix", "suffix", "nickname") if name.get(k)]
    if name.get("also"):
        pairs.append(("also", "[" + ", ".join(quote(n) for n in name["also"]) + "]"))
    for key, value in (name.get("extra") or {}).items():
        pairs.append((key, _any(value)))
    if pairs:
        lines += _line("  ", "name", pairs)
    if spec.get("sex") and spec["sex"] != "unknown":
        lines.append(f"  sex: {quote(spec['sex'], flow=False)}")
    for key in ("birth", "death"):
        value = spec.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            lines.append(f"  {key}: {quote(value, flow=False)}")
        else:
            lines += _line("  ", key, _fact(**value), only_date=True)
    if spec.get("parents"):
        lines.append("  parents: [" + ", ".join(quote(p) for p in spec["parents"]) + "]")
    lines += _events(spec.get("events") or [])
    if spec.get("portrait"):
        lines.append(f"  portrait: {quote(spec['portrait'], flow=False)}")
    if spec.get("living"):
        lines.append("  living: true")
    refs = [(k, quote(spec["refs"][k])) for k in ("gedcom", "gallery") if (spec.get("refs") or {}).get(k)]
    if refs:
        lines.append(f"  refs: {_flow(refs)}")
    for key, value in (spec.get("x") or {}).items():
        lines.append(f"  {key}: {_any(value)}")
    lines += _bio(spec.get("bio") or "")
    return "\n".join(lines) + "\n"


def couple(a: str, b: str, spec: dict | None = None) -> str:
    """One couple record (`a + b`, ids sorted). `spec` keys: events (list of entries), note, x."""
    a, b = sorted((a, b))
    spec = spec or {}
    entries, note, extras = spec.get("events") or [], spec.get("note"), spec.get("x") or {}
    if not (entries or note or extras):
        return f"{a} + {b}: {{}}\n"
    lines = [f"{a} + {b}:"] + _events(entries)
    if note:
        lines.append(f"  note: {quote(note, flow=False)}")
    for key, value in extras.items():
        lines.append(f"  {key}: {_any(value)}")
    return "\n".join(lines) + "\n"


def family(people: list[tuple[str, dict]], couples: list[tuple[str, str, dict]], header: str = "") -> str:
    """The whole file: people by id, each couple directly after its second partner (the later id), blank lines between."""
    by_second: dict[str, list] = {}
    loose: list = []
    known = {pid for pid, _ in people}
    for a, b, spec in sorted(couples, key=lambda c: tuple(sorted(c[:2]))):
        first, second = sorted((a, b))
        (by_second.setdefault(second, []) if second in known and first in known else loose).append((first, second, spec))
    blocks: list[str] = []
    for pid, spec in sorted(people):
        blocks.append(person(pid, spec))
        blocks += [couple(first, second, cspec) for first, second, cspec in by_second.get(pid, [])]
    blocks += [couple(first, second, cspec) for first, second, cspec in loose]
    body = "\n".join(blocks)
    return (header.rstrip("\n") + "\n\n" if header else "") + body


def spec_from_person(p) -> dict:
    """The emit spec of a model `Person` (as the legacy reader and the GEDCOM importer produce it)."""

    def vital(event):
        if event is None:
            return None
        extra = dict(event.extra)
        note, cite = extra.pop("note", None), extra.pop("cite", None)
        only_date = event.date and not (event.place or note or cite or extra)
        if only_date:
            return event.date
        if not (event.date or event.place or note or cite or extra):
            return None
        return {"date": event.date, "place": event.place, "note": note, "cite": cite, "extra": extra}

    events = []
    for e in p.events:
        events.append(
            {"type": e.type, "date": e.date, "start": e.start, "end": e.end, "place": e.place, "value": e.value,
             "note": e.note, "cite": e.cite, "extra": e.extra}
        )
    return {
        "name": {"given": p.given, "surname": p.surname, "prefix": p.prefix, "suffix": p.suffix, "nickname": p.nickname,
                 "also": list(p.also), "extra": dict(p.name_extra)},
        "sex": {"M": "male", "F": "female"}.get(p.sex, "unknown"),
        "birth": vital(p.birth),
        "death": vital(p.death),
        "parents": list(p.parents),
        "events": events,
        "portrait": p.portrait,
        "living": p.living is True,
        "refs": {"gedcom": p.gedcom_id, "gallery": p.gallery_id},
        "x": dict(p.extra),
        "bio": p.body,
    }


__all__ = ["quote", "person", "couple", "family", "spec_from_person", "event_pairs", "parse_span"]
