from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .dates import parse_date
from .model import Tree
from .living import is_living
from .relations import Relations


@dataclass
class Gap:
    id: str
    name: str
    missing: list[str] = field(default_factory=list)
    relatives: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "missing": self.missing, "relatives": self.relatives}


def find_gaps(tree: Tree, relations: Relations, *, today: date, cutoff_years: int = 100) -> list[Gap]:
    """People with something missing, best-connected first. Nothing is inferred: only absent facts are listed."""
    gaps: list[Gap] = []
    for pid, person in tree.people.items():
        missing: list[str] = []
        if not (person.given or person.surname):
            missing.append("name")
        if not (person.birth and parse_date(person.birth.date)):
            missing.append("birth date")
        if not (person.birth and person.birth.place):
            missing.append("birth place")
        if not is_living(person, today, cutoff_years) and not (person.death and parse_date(person.death.date)):
            missing.append("death date")
        if not relations.parents.get(pid):
            missing.append("parents")
        if not missing:
            continue
        kin = set(relations.parents.get(pid, []))
        for cid in relations.couples_of.get(pid, []):
            kin.update(x for x in relations.couples[cid].partners if x != pid)
            kin.update(relations.kids.get(cid, []))
        kin.discard(pid)
        gaps.append(Gap(pid, person.display_name, missing, len(kin)))
    gaps.sort(key=lambda g: (-g.relatives, g.name.lower(), g.id))
    return gaps
