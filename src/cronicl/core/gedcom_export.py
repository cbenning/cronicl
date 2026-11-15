"""Write a family as a GEDCOM 5.5.1 file (UTF-8), the mirror of the importer in `gedcom.py`.

The export reads the loaded `Tree`; it never touches the data folder. A person the privacy settings treat as living is
written as a placeholder (`NAME Living`, links only) or left out, exactly as the site would show them.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date

from .dates import parse_span, to_gedcom
from .issues import Issue
from .living import counts_as_death, is_living
from .model import Person, Tree
from .textvalues import cites_of, normal_type
from .yamltext import load_text

# The inverse of gedcom._EVENT_TAGS: event type -> (tag, whether the value is the line's own text).
_TAG_FOR_TYPE = {
    "baptism": ("BAPM", False), "christening": ("CHR", False), "confirmation": ("CONF", False),
    "burial": ("BURI", False), "cremation": ("CREM", False), "immigration": ("IMMI", False),
    "emigration": ("EMIG", False), "naturalization": ("NATU", False), "residence": ("RESI", False),
    "occupation": ("OCCU", True), "education": ("EDUC", True), "religion": ("RELI", True),
    "nationality": ("NATI", True), "graduation": ("GRAD", False), "retirement": ("RETI", False),
    "census": ("CENS", False), "will": ("WILL", False), "probate": ("PROB", False),
}
_PARTNERSHIP_TYPES = ("marriage", "civil-union", "partnership", "engagement", "divorce", "annulment", "separation", "end")
_MAPPED_TAGS = {"BIRT", "DEAT", "NAME", "NOTE", *(tag for tag, _ in _TAG_FOR_TYPE.values())}
_XREF_OK = re.compile(r"^[A-Za-z0-9_]{1,20}$")
_EXTRA_LINE = re.compile(r"^\s*(\d+) (?:(@[^@\s]+@) )?(\S+)(?: (.*))?$")
_POINTER_VALUE = re.compile(r"^@[^@\s]+@$")
_CHUNK = 200  # characters of text per physical line; GEDCOM allows 255 including the level and tag


def read_gedcom_extra(text: str | None) -> dict[str, str]:
    """`archive/gedcom-extra.yml` (what the importer set aside, by person id) as {person id: GEDCOM lines}."""
    if not text:
        return {}
    data = load_text(text).data
    return {str(k): v for k, v in data.items() if isinstance(data, dict) and isinstance(v, str)} if isinstance(data, dict) else {}


def _coordinate(value: float, positive: str, negative: str) -> str:
    return f"{positive if value >= 0 else negative}{abs(value):.6f}".rstrip("0").rstrip(".")


class _Writer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, level: int, tag: str, value: str = "", xref: str = "", *, pointer: bool = False) -> None:
        """One logical line; a value with newlines or beyond `_CHUNK` characters continues with CONT / CONC.

        Text has its `@` doubled (GEDCOM's escape); a `pointer` (`@F1@`) is written as it is."""
        text = value or "" if pointer else (value or "").replace("@", "@@")
        parts = text.split("\n")
        head = f"{level} " + (f"{xref} " if xref else "") + tag
        self._put(head, parts[0], level + 1)
        for part in parts[1:]:
            self._put(f"{level + 1} CONT", part, level + 1)

    def _put(self, head: str, text: str, child_level: int) -> None:
        first, rest = text[:_CHUNK], text[_CHUNK:]
        self.lines.append(head + (f" {first}" if first else ""))
        while rest:
            piece, rest = rest[:_CHUNK], rest[_CHUNK:]
            self.lines.append(f"{child_level} CONC {piece}")

    def raw(self, text: str) -> None:
        self.lines.extend(text.split("\n"))


def _date_text(value: str | None) -> str | None:
    return to_gedcom(value) if value else None


def _span(start: str | None, end: str | None) -> str | None:
    if start and end:
        return f"FROM {start} TO {end}"
    return f"FROM {start}" if start else (f"TO {end}" if end else None)


class _Export:
    def __init__(self, tree: Tree, mode: str, cutoff: int, today: date, places: dict, extra: dict, include_living: bool):
        self.tree, self.places, self.extra = tree, places, extra
        self.issues: list[Issue] = []
        redacting = mode in ("placeholder", "hidden") and not include_living
        self.living = {pid for pid, p in tree.people.items() if redacting and is_living(p, today, cutoff)}
        self.places = {" ".join(str(k).split()).casefold(): v for k, v in places.items()}
        self.hidden = self.living if mode == "hidden" else set()
        self.today = today
        self.cites: dict[str, str] = {}
        self.out = _Writer()
        self.person_xref: dict[str, str] = {}
        self.sources: dict[str, str] = {}

    # ---- cross references -------------------------------------------------------------------------------------
    def assign_xrefs(self) -> None:
        """Person references: `refs.gedcom` when usable and unique, else the next free `I<n>`. A redacted person never
        keeps the original reference, and their numbers follow a hash of the id, not the sorted ids (which spell names)."""
        taken: set[str] = {"SUBM"}
        want: dict[str, str] = {}
        for pid in sorted(self.tree.people):
            ref = (self.tree.people[pid].gedcom_id or "").strip("@")
            if pid not in self.living and pid not in self.hidden and _XREF_OK.match(ref) and ref not in taken:
                taken.add(ref)
                want[pid] = ref
        shown = [pid for pid in sorted(self.tree.people) if pid not in self.hidden]
        order = [p for p in shown if p not in self.living] + sorted(
            (p for p in shown if p in self.living), key=lambda p: hashlib.sha256(p.encode()).hexdigest()
        )
        counter = 0
        for pid in order:
            if pid in want:
                self.person_xref[pid] = f"@{want[pid]}@"
                continue
            while True:
                counter += 1
                candidate = f"I{counter}"
                if candidate not in taken:
                    taken.add(candidate)
                    self.person_xref[pid] = f"@{candidate}@"
                    break
        self.taken = taken
        self.order = order

    def fresh(self, prefix: str, number: int) -> str:
        """`@<prefix><n>@`, moved on past any reference a person already uses."""
        while f"{prefix}{number}" in self.taken:
            number += 1
        self.taken.add(f"{prefix}{number}")
        return f"@{prefix}{number}@"

    def source_xref(self, text: str) -> str:
        return self.sources[text]

    # ---- fact blocks -------------------------------------------------------------------------------------------
    def fact_tail(self, level: int, *, date_text=None, place=None, note=None, cites=()) -> None:
        w = self.out
        if date_text:
            w.line(level, "DATE", date_text)
        if place:
            w.line(level, "PLAC", place)
            coords = self.places.get(" ".join(place.split()).casefold())
            if coords:
                w.line(level + 1, "MAP")
                w.line(level + 2, "LATI", _coordinate(coords[0], "N", "S"))
                w.line(level + 2, "LONG", _coordinate(coords[1], "E", "W"))
        if note:
            w.line(level, "NOTE", note)
        for text in cites:
            w.line(level, "SOUR", self.source_xref(text), pointer=True)

    def vital(self, tag: str, event, *, unknown_means_y: bool = False) -> None:
        if event is None:
            return
        extra = event.extra or {}
        date_text = _date_text(event.date)
        note = extra.get("note") if isinstance(extra.get("note"), str) else None
        cites = cites_of(extra.get("cite"))
        if not (date_text or event.place or note or cites):
            if unknown_means_y:
                self.out.line(1, tag, "Y")
            return
        self.out.line(1, tag)
        self.fact_tail(2, date_text=date_text, place=event.place, note=note, cites=cites)

    def life_event(self, e) -> None:
        date_text = _date_text(e.date) if e.date else _span(_date_text(e.start), _date_text(e.end))
        tag, takes_value = _TAG_FOR_TYPE.get(e.type, ("EVEN", True))
        payload = (e.value or "") if takes_value else ""
        self.out.line(1, tag, payload)
        if tag == "EVEN":
            self.out.line(2, "TYPE", e.type)
        self.fact_tail(2, date_text=date_text, place=e.place, note=e.note, cites=e.cite)

    # ---- records -----------------------------------------------------------------------------------------------
    def collect_cites(self, people: list[Person], fam_entries: list, extras: list = ()) -> None:
        found: set[str] = set()
        for person in people:
            for vital in (person.birth, person.death):
                if vital is not None:
                    found.update(cites_of((vital.extra or {}).get("cite")))
            for e in person.events:
                found.update(e.cite)
        for entry in fam_entries:
            found.update(entry.cite)
        for entry in extras:
            found.update(cites_of(entry.get("cite")))
        for number, text in enumerate(sorted(found), start=1):
            self.sources[text] = self.fresh("S", number)

    def run(self) -> str:
        tree, w = self.tree, self.out
        people = [tree.people[pid] for pid in sorted(tree.people) if pid not in self.hidden]
        self.assign_xrefs()
        fams = self.plan_families()
        shown_entries = [e for fam in fams for e in fam["entries"]]
        self.collect_cites([p for p in people if p.id not in self.living], shown_entries, [e for fam in fams for e in fam.get("extras", [])])

        from .. import __version__

        w.raw("0 HEAD")
        w.line(1, "SOUR", "cronicl")
        w.line(2, "NAME", "cronicl")
        w.line(2, "VERS", __version__)
        w.line(1, "DEST", "ANY")
        w.line(1, "DATE", to_gedcom(self.today.isoformat()) or "")
        w.raw("1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n1 SUBM @SUBM@")
        w.raw("0 @SUBM@ SUBM\n1 NAME cronicl")

        famc: dict[str, str] = {}
        fams_of: dict[str, list[str]] = {}
        for fam in fams:
            for child in fam["children"]:
                famc.setdefault(child, fam["xref"])
            for pid in fam["partners"]:
                fams_of.setdefault(pid, []).append(fam["xref"])
        by_id = {p.id: p for p in people}
        for pid in sorted(by_id, key=lambda i: (i in self.living, "" if i not in self.living else hashlib.sha256(i.encode()).hexdigest(), i)):
            self.individual(by_id[pid], famc.get(pid), fams_of.get(pid, []))
        for fam in fams:
            self.family(fam)
        for text, xref in sorted(self.sources.items(), key=lambda item: item[0]):
            w.line(0, "SOUR", "", xref)
            w.line(1, "TITL", text)
        w.raw("0 TRLR")
        return "\n".join(w.lines) + "\n"

    def individual(self, person: Person, famc: str | None, fams: list[str]) -> None:
        w = self.out
        xref = self.person_xref[person.id]
        w.line(0, "INDI", "", xref)
        if person.id in self.living:  # placeholder: a living person is a name-less node with links
            w.line(1, "NAME", "Living")
        else:
            given = (person.given or "").replace("/", " ")
            surname = (person.surname or "").replace("/", " ")
            w.line(1, "NAME", f"{given} /{surname}/".strip() if surname or given else "")
            for tag, value in (("GIVN", person.given), ("SURN", person.surname), ("NPFX", person.prefix), ("NSFX", person.suffix), ("NICK", person.nickname)):
                if value:
                    w.line(2, tag, value)
            for other in person.also:
                w.line(1, "NAME", other.replace("/", " "))
                w.line(2, "TYPE", "aka")
            if person.sex in ("M", "F") or "\n1 SEX " not in "\n" + self.extra.get(person.id, ""):
                w.line(1, "SEX", {"M": "M", "F": "F"}.get(person.sex, "U"))
            self.vital("BIRT", person.birth)
            self.vital("DEAT", person.death if counts_as_death(person.death) else None, unknown_means_y=True)
            for event in person.events:
                self.life_event(event)
            if person.body:
                w.line(1, "NOTE", person.body)
            if person.id in self.extra:
                w.raw(self.person_extra(person.id))
        if famc:
            w.line(1, "FAMC", famc, pointer=True)
        for ref in fams:
            w.line(1, "FAMS", ref, pointer=True)

    def person_extra(self, pid: str) -> str:
        """The lines the importer set aside for a person, safe to write again.

        Their text is escaped again (the importer read `@@` as `@`). A line that points at another record (`@S9@`) or
        belongs to a family block is dropped with its sub-lines: the records it named are not in this file, and our
        numbering differs from the original's, so a kept pointer could link to the wrong record. What was set aside
        under a tag the importer maps (`1 BURI` with an `AGE` line) is written under `_BURI`: written as BURI it would
        be a second burial, and re-importing it would invent an event each time round.
        """
        blocks: list[list[str]] = []  # one entry per level-1 line: [head, its sub-lines...]
        skipping_from: int | None = None
        dropped_family = dropped_pointer = False
        for raw in self.extra[pid].split("\n"):
            match = _EXTRA_LINE.match(raw)
            if not match:
                continue
            level, xref, tag, value = int(match.group(1)), match.group(2), match.group(3), match.group(4) or ""
            if skipping_from is not None and level > skipping_from:
                continue
            skipping_from = None
            if level == 0:
                skipping_from, dropped_family = 0, True
                continue
            if xref or _POINTER_VALUE.match(value.strip()):
                skipping_from, dropped_pointer = level, True
                continue
            if level == 1:
                tag = "_" + tag if tag in _MAPPED_TAGS else tag
                blocks.append([])
            if not blocks:
                continue
            text = value.replace("@", "@@")
            blocks[-1].append(f"{level} {tag}" + (f" {text[:_CHUNK]}" if text else ""))
            for start in range(_CHUNK, len(text), _CHUNK):
                blocks[-1].append(f"{level + 1} CONC {text[start:start + _CHUNK]}")
        if dropped_family:
            self.issues.append(Issue("W-GEDCOM-EXTRA-FAM", f"{pid}: lines about a family in archive/gedcom-extra.yml are not exported"))
        if dropped_pointer:
            self.issues.append(Issue("W-GEDCOM-EXTRA-POINTER", f"{pid}: lines in archive/gedcom-extra.yml that point at other records are not exported"))
        kept = [b for b in blocks if len(b) > 1 or " " in b[0].split(" ", 1)[1].strip()]  # a bare parent says nothing
        return "\n".join(line for block in kept for line in block)

    # ---- families ----------------------------------------------------------------------------------------------
    def plan_families(self) -> list[dict]:
        """One FAM per partnership of a couple, a bare FAM for a couple with none, and one per set of parents."""
        people = self.tree.people
        entries: dict[tuple, list] = {}
        for pid in sorted(people):
            for p in people[pid].partnerships:
                if p.with_id in people and p.with_id != pid:
                    entries.setdefault(tuple(sorted((pid, p.with_id))), []).append(p)
            for other in people[pid].spouse:
                if other in people and other != pid:
                    entries.setdefault(tuple(sorted((pid, other))), [])
        kids: dict[tuple, list[str]] = {}
        for pid in sorted(people):
            parents = tuple(sorted(x for x in people[pid].parents if x in people))[:2]
            if parents:
                kids.setdefault(parents, []).append(pid)
                entries.setdefault(parents, [])
        fams: list[dict] = []
        number = 0
        for key in sorted(entries):
            partners = [x for x in key if x not in self.hidden]
            children = [c for c in kids.get(key, []) if c not in self.hidden]
            if not partners or (len(partners) == 1 and not children):
                continue
            redacted = any(x in self.living for x in key)
            groups = [None] if redacted else (entries[key] or [None])
            for index, entry in enumerate(groups):
                number += 1
                fams.append({
                    "xref": self.fresh("F", number), "partners": partners, "key": key, "entries": [] if redacted or entry is None else [entry],
                    "children": children if index == 0 else [],
                    "extras": [] if redacted or index else self.other_couple_events(key),
                })
        return fams

    def other_couple_events(self, key: tuple) -> list:
        """A couple record's events of types that do not begin or end a partnership (a residence, a census): kept as EVEN."""
        first = self.tree.people.get(key[0])
        out = []
        for other, record, *_ in getattr(first, "couple_records", []):
            if other != key[-1] or not hasattr(record, "get"):
                continue
            for entry in record.get("events") or []:
                kind = entry.get("type") if hasattr(entry, "get") else None
                if isinstance(kind, str) and kind.strip() and normal_type(kind) not in _PARTNERSHIP_TYPES:
                    out.append(entry)
        return out

    def roles(self, partners: list[str]) -> list[tuple[str, str]]:
        people = self.tree.people

        def sex(pid: str) -> str:
            return "U" if pid in self.living else people[pid].sex  # a placeholder says nothing about sex

        if len(partners) == 1:
            only = partners[0]
            return [("WIFE" if sex(only) == "F" else "HUSB", only)]
        a, b = partners
        if (sex(a) == "F" and sex(b) != "F") or (sex(b) == "M" and sex(a) != "M"):
            a, b = b, a
        return [("HUSB", a), ("WIFE", b)]

    def family(self, fam: dict) -> None:
        w = self.out
        w.line(0, "FAM", "", fam["xref"])
        for tag, pid in self.roles(fam["partners"]):
            w.line(1, tag, self.person_xref[pid], pointer=True)
        for child in fam["children"]:
            w.line(1, "CHIL", self.person_xref[child], pointer=True)
        for p in fam["entries"]:
            self.partnership(p)
        for entry in fam.get("extras", []):
            value = entry.get("value")
            w.line(1, "EVEN", value.strip() if isinstance(value, str) and value.strip() else "")
            w.line(2, "TYPE", entry["type"].strip())
            note = entry.get("note")
            self.fact_tail(2, date_text=_date_text(entry.get("date")) if isinstance(entry.get("date"), str) else None,
                           place=entry.get("place") if isinstance(entry.get("place"), str) else None,
                           note=note if isinstance(note, str) and note.strip() else None, cites=cites_of(entry.get("cite")))

    def partnership(self, p) -> None:
        w = self.out
        begin = {"marriage": "MARR", "engagement": "ENGA"}.get(p.type or "")
        if begin or p.start or p.place or p.note or p.cite or p.type:
            if begin:  # the importer only believes a MARR/ENGA that has a DATE or PLAC, or says Y
                w.line(1, begin, "" if (p.start and _date_text(p.start)) or p.place else "Y")
            else:
                w.line(1, "EVEN")
                w.line(2, "TYPE", p.type or "partnership")
            self.fact_tail(2, date_text=_date_text(p.start), place=p.place, note=p.note, cites=p.cite)
        if p.end is not None:
            tag = {"divorce": "DIV", "annulment": "ANUL"}.get(p.end_reason or "")
            end_date = _date_text(p.end)
            if tag:
                w.line(1, tag, "" if end_date else "Y")
            else:
                w.line(1, "EVEN")
                w.line(2, "TYPE", p.end_reason or "end")
            if end_date:
                w.line(2, "DATE", end_date)


def export_gedcom(
    tree: Tree, *, mode: str = "full", cutoff: int = 100, today: date | None = None, places: dict | None = None,
    extra: dict | None = None, include_living: bool = False,
) -> tuple[str, list[Issue]]:
    """The tree as GEDCOM 5.5.1 text and the issues met on the way.

    `mode` is the site's `privacy.living` (`full`, `placeholder`, `hidden`); `places` maps a casefolded place name to
    (lat, lon); `extra` maps a person id to GEDCOM lines the importer set aside.
    """
    export = _Export(tree, mode, cutoff, today or date.today(), places or {}, extra or {}, include_living)
    text = export.run()
    return text, export.issues


__all__ = ["export_gedcom", "read_gedcom_extra", "parse_span"]
