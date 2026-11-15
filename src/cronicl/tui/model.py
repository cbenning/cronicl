"""The family as the TUI sees it: the texts of the files, the tree read from them, and every issue `check` reports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..checks import check_all
from ..checktext import load_tree_from_texts
from ..core.dates import format_years
from ..core.family import family_files
from ..core.issues import Issue
from ..core.living import is_living
from ..core.model import Tree
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
        return Row(pid, person.display_name if person.display_name != pid else pid, years, place or "", is_living(person, self.today, self.cutoff), counts.get(pid, 0))

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

    def living_count(self) -> int:
        return sum(1 for p in self.tree.people.values() if is_living(p, self.today, self.cutoff))
