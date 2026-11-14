"""Reading `family.yml` (or a `family/` folder of the same format) into the in-memory model.

A top-level key is a record: a person id, or a couple (`a + b`). The model stays the one the rest of cronicl knows:
a couple's begin/end events become `Partnership`s on the first-sorting partner, and an empty couple becomes a
`spouse` link, so relations, layout and the timeline read the same objects as before.
"""
from __future__ import annotations

import re
from pathlib import Path

from .dates import parse_span, plain_form
from .issues import Issue
from .model import Event, LifeEvent, Partnership, Person
from .textvalues import parse_bool
from .yamltext import Mapping, Sequence, load_text

ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COUPLE = re.compile(r"^\s*(\S+?)\s*\+\s*(\S+?)\s*$")
BEGIN = ("marriage", "civil-union", "partnership", "engagement")
END = ("divorce", "annulment", "separation", "end")
SEX = {"male": "M", "female": "F", "unknown": "U", "other": "U"}
NAME_KEYS = ("given", "surname", "prefix", "suffix", "nickname", "also")


def family_files(data_dir: Path) -> list[Path]:
    """The files that make up the family: family.yml, or the .yml files of family/ in sorted order."""
    single, folder = data_dir / "family.yml", data_dir / "family"
    if single.is_file():
        return [single]
    if folder.is_dir():
        return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix == ".yml")
    return []


def has_family(data_dir: Path) -> bool:
    data_dir = Path(data_dir)
    return (data_dir / "family.yml").exists() or (data_dir / "family").is_dir()


def _text(value) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    return None


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


class _Reader:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.issues: list[Issue] = []
        self.people: dict[str, Person] = {}
        self.couples: list[tuple] = []  # (a, b, record, source, line)
        self.seen_couples: set[tuple[str, str]] = set()

    def problem(self, code: str, message: str, source: str, line: int | None = None) -> None:
        self.issues.append(Issue(code, message, source, line))

    # ---- one dated fact or event -------------------------------------------------------------------------------
    def _vital(self, record: Mapping, key: str, pid: str, source: str):
        value = record.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return Event(date=text) if text else None
        if isinstance(value, Mapping):
            event = Event(date=_text(value.get("date")), place=_text(value.get("place")))
            event.extra = {k: v for k, v in value.items() if k not in ("date", "place")}
            return event if not event.is_empty() else None
        self.problem("E-RECORD-SHAPE", f"{pid}: {key} must be a date or a mapping (date, place, note, cite)", source, record.lines.get(key))
        return None

    def _events(self, record: Mapping, pid: str, source: str) -> list[dict]:
        value = record.get("events")
        if value is None or value == "":
            return []
        if not isinstance(value, Sequence) or any(not isinstance(item, Mapping) for item in value):
            self.problem("E-RECORD-SHAPE", f"{pid}: events must be a list of mappings", source, record.lines.get("events"))
            return []
        return list(value)

    # ---- records -----------------------------------------------------------------------------------------------
    def person(self, pid: str, record, source: str, line: int) -> None:
        if record == "":
            record = Mapping()
            record.line = line
        if not isinstance(record, Mapping):
            self.problem("E-RECORD-SHAPE", f"{pid}: a person record must be a mapping of facts", source, line)
            return
        person = Person(id=pid, source=source, line=line, raw=record, path=self.data_dir / source)
        name = record.get("name")
        if name is not None and name != "":
            if isinstance(name, Mapping):
                person.given, person.surname = _text(name.get("given")), _text(name.get("surname"))
                person.prefix, person.suffix = _text(name.get("prefix")), _text(name.get("suffix"))
                person.nickname = _text(name.get("nickname"))
                person.also = _texts(name.get("also"))
                person.name_extra = {k: v for k, v in name.items() if k not in NAME_KEYS}
            else:
                self.problem("E-RECORD-SHAPE", f"{pid}: name must be a mapping (given, surname, ...)", source, record.lines.get("name"))
        sex = _text(record.get("sex"))
        person.sex_text = sex
        person.sex = SEX.get((sex or "").casefold(), "U")
        person.birth = self._vital(record, "birth", pid, source)
        person.death = self._vital(record, "death", pid, source)
        parents = record.get("parents")
        if parents is not None and parents != "":
            if isinstance(parents, Sequence) and all(isinstance(p, str) for p in parents):
                person.parents = [p.strip() for p in parents if p.strip()]
            else:
                self.problem("E-RECORD-SHAPE", f"{pid}: parents must be a list of person ids", source, record.lines.get("parents"))
        for entry in self._events(record, pid, source):
            person.events.append(self._life_event(entry))
        person.portrait = _text(record.get("portrait"))
        living = record.get("living")
        if isinstance(living, str):
            person.living_text = living.strip()
            # only `living: true` counts; anything else is reported (W-LIVING-FALSE) and ignored, so privacy fails closed
            person.living = True if parse_bool(living) is True else None
        refs = record.get("refs")
        if isinstance(refs, Mapping):
            person.gedcom_id = _text(refs.get("gedcom"))
            person.gallery_id = _text(refs.get("gallery"))
        bio = record.get("bio")
        person.body = bio.strip("\n") if isinstance(bio, str) else ""
        known = {"name", "sex", "birth", "death", "parents", "events", "portrait", "living", "refs", "bio"}
        person.extra = {k: v for k, v in record.items() if k not in known}
        self.people[pid] = person

    @staticmethod
    def _life_event(entry: Mapping) -> LifeEvent:
        event = LifeEvent(type=_text(entry.get("type")) or "")
        date = _text(entry.get("date"))
        span = parse_span(date) if date else None
        if span:
            event.start, event.end = span
        else:
            event.date = date
        event.place, event.value, event.note = _text(entry.get("place")), _text(entry.get("value")), _text(entry.get("note"))
        event.cite = _texts(entry.get("cite"))
        event.extra = {k: v for k, v in entry.items() if k not in ("type", "date", "place", "value", "note", "cite")}
        return event

    def couple(self, key: str, match, record, source: str, line: int) -> None:
        a, b = match.group(1), match.group(2)
        if not (ID.match(a) and ID.match(b)):
            self.problem("E-RECORD-KEY", f"{key!r} is not a person id or a couple of two person ids joined by +", source, line)
            return
        if a == b:
            self.problem("E-COUPLE-SELF", f"{key!r}: a couple needs two different people", source, line)
            return
        pair = tuple(sorted((a, b)))
        if pair in self.seen_couples:
            self.problem("E-DUPLICATE-ID", f"the couple {pair[0]} + {pair[1]} is written twice", source, line)
            return
        self.seen_couples.add(pair)
        if record == "":
            record = Mapping()
            record.line = line
        if not isinstance(record, Mapping):
            self.problem("E-RECORD-SHAPE", f"{key}: a couple record must be a mapping (events, note)", source, line)
            return
        self.couples.append((pair[0], pair[1], record, source, line))

    # ---- couples become partnerships ---------------------------------------------------------------------------
    def attach_couples(self) -> None:
        for a, b, record, source, line in self.couples:
            missing = [x for x in (a, b) if x not in self.people]
            if missing:
                self.problem("E-DANGLING-REF", f"{a} + {b}: {missing[0]} is not a person in the family", source, line)
                continue
            entries = self._events(record, f"{a} + {b}", source)
            for index, entry in enumerate(entries):
                kind = _text(entry.get("type")) or ""
                if kind not in BEGIN + END:
                    self.problem(
                        "W-COUPLE-EVENT",
                        f"{a} + {b}: event type {kind!r} is not one a couple can have ({', '.join(BEGIN + END)})",
                        source,
                        record.get("events").lines[index] if isinstance(record.get("events"), Sequence) else line,
                    )
            partnerships = partnerships_from_events(entries, b)
            note = _text(record.get("note"))
            if note:
                if partnerships:
                    partnerships[0].note = partnerships[0].note or note
                else:
                    partnerships.append(Partnership(with_id=b, note=note))
            first = self.people[a]
            first.couple_records.append((b, record, source, line))
            if partnerships:
                first.partnerships.extend(partnerships)
            else:
                first.spouse.append(b)


def partnerships_from_events(entries, other: str) -> list[Partnership]:
    """A couple's events (mappings with type, date, place, note, cite) as the Partnerships the model carries.

    Events are taken in date order (undated ones keep their written place). A beginning event starts a partnership; an
    ending event closes the latest open one, or makes a partnership of its own when nothing is open.
    """
    entries = [e for e in entries if (_text(e.get("type")) or "") in BEGIN + END]
    partnerships: list[Partnership] = []
    for entry in _in_date_order(entries):
        kind, date = _text(entry.get("type")), _text(entry.get("date"))
        if kind in BEGIN:
            partnerships.append(
                Partnership(with_id=other, distinct=True, type=kind, start=date, place=_text(entry.get("place")), note=_text(entry.get("note")),
                            cite=_texts(entry.get("cite")))
            )
            continue
        open_ones = [p for p in partnerships if p.end is None]
        target = open_ones[-1] if open_ones else None
        if target is None and partnerships and partnerships[-1].end_reason == "separation" and kind in ("divorce", "annulment"):
            target = partnerships[-1]  # separated, then divorced: the same partnership, ended for its final reason
        if target is None:
            target = Partnership(with_id=other, distinct=True)
            partnerships.append(target)
        target.end = date or "unknown"
        target.end_reason = kind if kind in ("divorce", "annulment", "separation") else None
        target.place = target.place or (None if target.start else _text(entry.get("place")))
        target.note = target.note or _text(entry.get("note"))
        target.cite = target.cite or _texts(entry.get("cite"))
    return partnerships


def _in_date_order(entries: list[Mapping]) -> list[Mapping]:
    """Order events by date; an event with no (readable) date keeps its written position among the others."""
    slots = [i for i, e in enumerate(entries) if plain_form(_text(e.get("date")))]
    dated = sorted((entries[i] for i in slots), key=lambda e: plain_form(_text(e.get("date"))))
    out = list(entries)
    for slot, entry in zip(slots, dated):
        out[slot] = entry
    return out


def read_family(data_dir: Path) -> tuple[list[Person], list[Issue]]:
    data_dir = Path(data_dir)
    reader = _Reader(data_dir)
    single, folder = data_dir / "family.yml", data_dir / "family"
    if single.exists() and folder.is_dir():
        reader.problem("E-BAD-FAMILY", "both family.yml and a family/ folder exist; keep one of them", "family.yml")
        return [], reader.issues
    seen_people: set[str] = set()
    for path in family_files(data_dir):
        source = path.relative_to(data_dir).as_posix()
        try:
            raw = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            reader.problem("E-BAD-FAMILY", f"cannot read {source}: {type(exc).__name__}", source)
            continue
        result = load_text(raw)
        if result.error:
            reader.problem("E-BAD-FAMILY", f"cannot parse {source}: {result.error}", source, result.error_line)
            continue
        top = set(result.top_duplicates)
        for key, line in result.duplicates:
            if (key, line) not in top:
                reader.problem("W-DUPLICATE-KEY", f"duplicate key {key!r}; the later value is used", source, line)
        for line in result.merge_keys:
            reader.problem("E-BAD-FAMILY", "merge keys (<<) are not supported; write the values out", source, line)
        if result.merge_keys:
            continue
        if not isinstance(result.data, Mapping):
            reader.problem("E-BAD-FAMILY", f"{source} must be a mapping of records (person ids and couples)", source, 1)
            continue
        for key, line in result.top_duplicates:
            reader.problem("E-DUPLICATE-ID", f"{key!r} is written twice; the later record is ignored", source, line)
        for key, value in result.data.items():
            line = result.data.lines.get(key, 1)
            if (key, line) in result.top_duplicates:
                continue  # the later copy of a repeated key
            match = COUPLE.match(key) if "+" in key else None
            if match:
                reader.couple(key, match, value, source, line)
            elif ID.match(key):
                if key in seen_people:
                    reader.problem("E-DUPLICATE-ID", f"{key!r} is already a person in another file", source, line)
                    continue
                seen_people.add(key)
                reader.person(key, value, source, line)
            else:
                reader.problem(
                    "E-RECORD-KEY",
                    f"{key!r} is neither a person id (lower-case letters, digits, hyphens) nor a couple of two ids joined by +",
                    source,
                    line,
                )
    reader.attach_couples()
    return list(reader.people.values()), reader.issues
