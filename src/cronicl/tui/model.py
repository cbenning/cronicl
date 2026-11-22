"""The family as the TUI sees it: the texts of the files, the tree read from them, and every issue `check` reports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..checks import check_all
from ..checktext import load_tree_from_texts
from ..core.dates import format_years, plain_form
from ..core.family import family_files
from ..core.issues import Issue
from ..core.living import is_living
from ..core.model import Tree
from ..core.relations import Relations, build_relations
from ..core.recordedit import _find_couple, _is_blank_document, _root
from ..core.search import search_people
from ..core.textvalues import parse_int


@dataclass
class Row:
    id: str
    name: str
    years: str
    place: str
    living: bool
    warnings: int
    parents: str = ""  # compact: the given names of the parents the tree draws, "George & Anne"
    children: str = ""  # compact: the first few children's given names, "Ada, Tom +2"


def read_disk(data_dir: Path) -> tuple[str | None, dict[str, str]]:
    """The text of site.yml (None when absent) and of each family file, exactly as stored (line endings kept)."""
    data_dir = Path(data_dir)
    site = data_dir / "site.yml"
    site_text = site.read_bytes().decode("utf-8") if site.is_file() else None
    files = {p.relative_to(data_dir).as_posix(): p.read_bytes().decode("utf-8") for p in family_files(data_dir)}
    return site_text, files


class Family:
    def __init__(self, data_dir: Path, site_text: str | None, files: dict[str, str], today: date | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.site_text, self.files = site_text, files
        self.today = today or date.today()
        self.tree, load = load_tree_from_texts(site_text, files, self.data_dir)
        self.issues: list[Issue] = check_all(self.tree, load)
        privacy = (self.tree.site or {}).get("privacy")
        self.cutoff = (parse_int(privacy.get("cutoff_years")) if isinstance(privacy, dict) else None) or 100
        self._owners = self._owners_by_line()
        self._relations: Relations | None = None

    @property
    def relations(self) -> Relations:
        if self._relations is None:
            self._relations = build_relations(self.tree)
        return self._relations

    def name_of(self, pid: str) -> str:
        person = self.tree.people.get(pid)
        return person.display_name if person else ""

    def years_of(self, pid: str) -> str:
        person = self.tree.people.get(pid)
        if person is None:
            return ""
        return format_years(person.birth.date if person.birth else None, person.death.date if person.death else None)

    def couple_key_text(self, a: str, b: str) -> tuple[str, str] | None:
        """(the couple's key as written in the file, the file) or None when the two have no couple record."""
        for pid in (a, b):
            for other, _, source, _line in self.tree.people[pid].couple_records:
                if other in (a, b) and other != pid:
                    text = self.files.get(source, "")
                    written = _find_couple(text, a, b)
                    if written:
                        return written, source
        return None

    def couple_summary(self, a: str, b: str) -> str:
        """`m. 1815-01-02 Seaham, England; divorced 1830` for the couple, or an empty string."""
        couple = self.relations.couples.get(tuple(sorted((a, b)))) if hasattr(self.relations, "couples") else None
        for cid, c in self.relations.couples.items():
            if set(c.partners) == {a, b}:
                couple = c
        if couple is None:
            return ""
        words = {"marriage": "m.", "civil-union": "civil union", "engagement": "engaged", "partnership": "partners"}
        parts = []
        for p in couple.partnerships:
            bit = words.get(p.type or "", "together")
            if p.start:
                bit += f" {p.start}"
            if p.place:
                bit += f" {p.place}"
            if p.end:
                bit += f"; {p.end_reason or 'ended'}" + (f" {p.end}" if p.end != "unknown" else "")
            parts.append(bit)
        return "; ".join(parts)

    @classmethod
    def load(cls, data_dir: Path, today: date | None = None) -> "Family":
        site_text, files = read_disk(data_dir)
        return cls(data_dir, site_text, files, today)

    # ---- who an issue belongs to ----------------------------------------------------------------------------------
    def _owners_by_line(self) -> dict[str, list[tuple[int, list[str]]]]:
        by_file: dict[str, list[tuple[int, list[str]]]] = {}
        for person in self.tree.people.values():
            if person.source is None or person.line is None:
                continue
            by_file.setdefault(person.source, []).append((person.line, [person.id]))
            for other, _, source, line in person.couple_records:
                by_file.setdefault(source, []).append((line, [person.id, other]))
        for entries in by_file.values():
            entries.sort(key=lambda e: e[0])
        return by_file

    def owners(self, issue: Issue) -> list[str]:
        """The people whose record holds the line an issue points at (a couple record belongs to both partners)."""
        entries = self._owners.get(issue.path or "", [])
        if issue.line is None:
            return []
        owner: list[str] = []
        for line, ids in entries:
            if line <= issue.line:
                owner = ids
            else:
                break
        return owner

    def issues_of(self, pid: str) -> list[Issue]:
        return [i for i in self.issues if pid in self.owners(i)]

    def warning_count(self, pid: str) -> int:
        return len(self.issues_of(pid))

    # ---- listing --------------------------------------------------------------------------------------------------
    def _row(self, pid: str, counts: dict[str, int]) -> Row:
        person = self.tree.people[pid]
        place = (person.birth.place if person.birth and person.birth.place else "") or (person.death.place if person.death and person.death.place else "")
        years = format_years(person.birth.date if person.birth else None, person.death.date if person.death else None)
        relations = self.relations
        parents = " & ".join(self._short(p, person.surname) for p in relations.parents.get(pid, []))
        kids = sorted(
            {k for cid in relations.couples_of.get(pid, []) for k in relations.kids.get(cid, [])},
            key=lambda k: (plain_form(self.tree.people[k].birth.date) if self.tree.people[k].birth and self.tree.people[k].birth.date else "\uffff", k),
        )
        children = ", ".join(self._short(k, person.surname) for k in kids[:2]) + (f" +{len(kids) - 2}" if len(kids) > 2 else "")
        return Row(pid, person.display_name if person.display_name != pid else pid, years, place or "", is_living(person, self.today, self.cutoff), counts.get(pid, 0), parents, children)

    def _short(self, pid: str, home: str | None = None) -> str:
        """A person in a few characters: the first given name, plus the surname when it is not `home`, else the whole name."""
        person = self.tree.people.get(pid)
        if person is None:
            return pid
        given = (person.given or "").split()
        if not given:
            return person.display_name
        return f"{given[0]} {person.surname}" if person.surname and person.surname != home else given[0]

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            for pid in self.owners(issue):
                counts[pid] = counts.get(pid, 0) + 1
        return counts

    def rows(self, query: str = "", limit: int = 200) -> list[Row]:
        counts = self.counts()
        query = query.strip()
        if not query:
            ordered = sorted(self.tree.people.values(), key=lambda p: ((p.surname or "").casefold(), (p.given or "").casefold(), p.id))
            return [self._row(p.id, counts) for p in ordered[:limit]]
        try:
            hits = search_people(self.tree, query, today=self.today, limit=limit)
        except ValueError:
            return []
        return [self._row(h.id, counts) for h in hits]

    def places(self) -> list[str]:
        """Every place written in the family, the most used first."""
        counts: dict[str, int] = {}

        def note(place):
            if place:
                counts[place] = counts.get(place, 0) + 1

        for person in self.tree.people.values():
            for event in (person.birth, person.death):
                note(event.place if event else None)
            for e in person.events:
                note(e.place)
            for p in person.partnerships:
                note(p.place)
        return [p for p, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))]

    def media_files(self) -> list[str]:
        folder = self.data_dir / "media"
        if not folder.is_dir():
            return []
        return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))

    def taken_ids(self) -> set[str]:
        """Every key already used as a record in the files, including records that are not people (a stray `a: oops`)."""
        taken = set(self.tree.people)
        for text in self.files.values():
            body = text.lstrip("\ufeff")
            if not body.strip() or _is_blank_document(body):
                continue
            try:
                taken.update(k.value for k, _ in _root(body).value)
            except Exception:  # noqa: BLE001 - an unreadable file adds nothing; staging refuses it anyway
                pass
        return taken

    def living_count(self) -> int:
        return sum(1 for p in self.tree.people.values() if is_living(p, self.today, self.cutoff))
