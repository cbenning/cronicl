"""Write a family as a GEDCOM 5.5.1 file (UTF-8), the mirror of the importer in `gedcom.py`.

The export reads the loaded `Tree`; it never touches the data folder. A person the privacy settings treat as living is
written as a placeholder (`NAME Living`, links only) or left out, exactly as the site would show them.
"""
from __future__ import annotations

import re
from datetime import date

from .dates import parse_span, to_gedcom
from .issues import Issue
from .living import is_living
from .model import Person, Tree
from .textvalues import cites_of
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
_XREF_OK = re.compile(r"^[A-Za-z0-9_]{1,20}$")
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
        self.hidden = self.living if mode == "hidden" else set()
        self.today = today
        self.cites: dict[str, str] = {}
        self.out = _Writer()
        self.person_xref: dict[str, str] = {}
        self.sources: dict[str, str] = {}

    # ---- cross references -------------------------------------------------------------------------------------
    def assign_xrefs(self) -> None:
        taken: set[str] = set()
        want: dict[str, str] = {}
        for pid in sorted(self.tree.people):
            ref = (self.tree.people[pid].gedcom_id or "").strip("@")
            if _XREF_OK.match(ref) and ref not in taken:
                taken.add(ref)
                want[pid] = ref
        counter = 0
        for pid in sorted(self.tree.people):
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

    def source_xref(self, text: str) -> str:
        return self.sources[text]

    # ---- fact blocks -------------------------------------------------------------------------------------------
    def fact_tail(self, level: int, *, date_text=None, place=None, note=None, cites=()) -> None:
        w = self.out
        if date_text:
            w.line(level, "DATE", date_text)
        if place:
            w.line(level, "PLAC", place)
            coords = self.places.get(place.strip().casefold())
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
    def collect_cites(self, people: list[Person], fam_entries: list) -> None:
        found: set[str] = set()
        for person in people:
            for vital in (person.birth, person.death):
                if vital is not None:
                    found.update(cites_of((vital.extra or {}).get("cite")))
            for e in person.events:
                found.update(e.cite)
        for entry in fam_entries:
            found.update(entry.cite)
        for number, text in enumerate(sorted(found), start=1):
            self.sources[text] = f"@S{number}@"

    def run(self) -> str:
        tree, w = self.tree, self.out
        people = [tree.people[pid] for pid in sorted(tree.people) if pid not in self.hidden]
        self.assign_xrefs()
        fams = self.plan_families()
        shown_entries = [e for fam in fams for e in fam["entries"]]
        self.collect_cites([p for p in people if p.id not in self.living], shown_entries)

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
        for person in people:
            self.individual(person, famc.get(person.id), fams_of.get(person.id, []))
        for fam in fams:
            self.family(fam)
        for text, xref in sorted(self.sources.items(), key=lambda item: int(item[1][2:-1])):
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
            self.vital("DEAT", person.death, unknown_means_y=True)
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
        lines = [l for l in self.extra[pid].split("\n") if l.strip()]
        keep: list[str] = []
        skipping = False
        for line in lines:
            level = line.split(" ", 1)[0]
            if level == "0":
                skipping = True
                continue
            if level == "1":
                skipping = False
            if not skipping:
                keep.append(line)
        if skipping or len(keep) != len(lines):
            self.issues.append(Issue("W-GEDCOM-EXTRA-FAM", f"{pid}: lines about a family in archive/gedcom-extra.yml are not exported"))
        return "\n".join(keep)

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
                    "xref": f"@F{number}@", "partners": partners, "key": key, "entries": [] if redacted or entry is None else [entry],
                    "children": children if index == 0 else [],
                })
        return fams

    def roles(self, partners: list[str]) -> list[tuple[str, str]]:
        people = self.tree.people
        if len(partners) == 1:
            only = partners[0]
            return [("WIFE" if people[only].sex == "F" else "HUSB", only)]
        a, b = partners
        if (people[a].sex == "F" and people[b].sex != "F") or (people[b].sex == "M" and people[a].sex != "M"):
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
