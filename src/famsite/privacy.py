from __future__ import annotations

import dataclasses
import hashlib
from datetime import date

from .dates import parse_date
from .model import Marriage, Person, Tree

MODES = ("hidden", "placeholder", "full")


def is_living(person: Person, today: date, cutoff_years: int = 100) -> bool:
    if person.living is not None:
        return person.living
    if person.death is not None:
        return False
    birth = parse_date(person.birth.date) if person.birth else None
    if birth is None:
        return True
    return today.year - birth.year < cutoff_years


def _anon(prefix: str, old: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{old}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def redact(
    tree: Tree,
    *,
    mode: str = "placeholder",
    today: date,
    cutoff_years: int = 100,
    salt: str = "",
) -> Tree:
    if mode not in MODES:
        raise ValueError(f"unknown privacy mode {mode!r}; expected one of {MODES}")
    living = {pid for pid, person in tree.people.items() if is_living(person, today, cutoff_years)}
    if mode == "full" or not living:
        return Tree(people=dict(tree.people), site=dict(tree.site))

    id_of: dict[str, str] = {}
    for pid in tree.people:
        if pid in living:
            if mode == "hidden":
                continue
            id_of[pid] = _anon("living", pid, salt)
        else:
            id_of[pid] = pid

    def remap(ids: list[str]) -> list[str]:
        return [id_of[x] for x in ids if x in id_of]

    out = Tree(site=dict(tree.site))
    for pid, person in tree.people.items():
        if pid not in id_of:
            continue
        if pid in living:
            out.people[id_of[pid]] = Person(
                id=id_of[pid],
                given="Living",
                sex="U",
                living=True,
                parents=remap(person.parents),
                spouse=remap(person.spouse),
                children=remap(person.children),
                marriages=[Marriage(id_of[m.with_id]) for m in person.marriages if m.with_id in id_of],
            )
        else:
            marriages = []
            for marriage in person.marriages:
                if marriage.with_id not in id_of:
                    continue
                private = marriage.with_id in living
                marriages.append(
                    Marriage(
                        id_of[marriage.with_id],
                        None if private else marriage.date,
                        None if private else marriage.place,
                    )
                )
            out.people[pid] = dataclasses.replace(
                person,
                parents=remap(person.parents),
                spouse=remap(person.spouse),
                children=remap(person.children),
                marriages=marriages,
                path=None,
            )
    return out
