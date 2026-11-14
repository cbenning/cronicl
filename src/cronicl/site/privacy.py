from __future__ import annotations

import dataclasses
import hashlib
from datetime import date

from ..core.living import is_living  # noqa: F401  (re-exported)
from ..core.model import Partnership, Person, Tree

MODES = ("hidden", "placeholder", "full")


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
                partnerships=[Partnership(id_of[p.with_id]) for p in person.partnerships if p.with_id in id_of],
            )
        else:
            partnerships = []
            for entry in person.partnerships:
                if entry.with_id not in id_of:
                    continue
                if entry.with_id in living:
                    partnerships.append(Partnership(id_of[entry.with_id]))  # the link survives, the details do not
                else:
                    partnerships.append(dataclasses.replace(entry, with_id=id_of[entry.with_id]))
            out.people[pid] = dataclasses.replace(
                person,
                parents=remap(person.parents),
                spouse=remap(person.spouse),
                children=remap(person.children),
                partnerships=partnerships,
                path=None,
            )
    return out
