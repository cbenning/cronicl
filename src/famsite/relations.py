from __future__ import annotations

from dataclasses import dataclass, field

from .issues import Issue
from .model import Event, Tree


@dataclass
class Couple:
    id: str
    partners: list[str]
    marriage: Event | None = None


@dataclass
class Relations:
    parents: dict[str, list[str]] = field(default_factory=dict)
    birth_couple: dict[str, str] = field(default_factory=dict)
    couples: dict[str, Couple] = field(default_factory=dict)
    kids: dict[str, list[str]] = field(default_factory=dict)
    couples_of: dict[str, list[str]] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)


def couple_id(partners: list[str]) -> str:
    ordered = sorted(partners)
    return "+".join(ordered) if len(ordered) > 1 else f"{ordered[0]}+"


def build_relations(tree: Tree) -> Relations:
    people = tree.people
    issues: list[Issue] = []

    def dangling(owner: str, field_name: str, target: str) -> None:
        issues.append(
            Issue("E-DANGLING-REF", f"{owner}: {field_name} {target!r} does not exist", people[owner].location)
        )

    # Effective parents: declared `parents` first, then down-declared `children`, in sorted order.
    declared: dict[str, list[str]] = {pid: [] for pid in people}
    for pid in sorted(people):
        for parent in people[pid].parents:
            if parent not in people:
                dangling(pid, "parents", parent)
            elif parent not in declared[pid]:
                declared[pid].append(parent)
    for pid in sorted(people):
        for child in people[pid].children:
            if child not in people:
                dangling(pid, "children", child)
            elif pid not in declared[child]:
                declared[child].append(pid)
    for pid in sorted(declared):
        if len(declared[pid]) > 2:
            issues.append(
                Issue(
                    "W-TOO-MANY-PARENTS",
                    f"{pid}: {len(declared[pid])} parents declared; using {declared[pid][:2]}",
                    people[pid].location,
                )
            )
            declared[pid] = declared[pid][:2]

    # Spouse and marriage pairs, declared on either end.
    pairs: set[tuple[str, ...]] = set()
    marriage_entries: dict[tuple[str, ...], list[Event]] = {}
    for pid in sorted(people):
        person = people[pid]
        for other in person.spouse:
            if other not in people:
                dangling(pid, "spouse", other)
            elif other == pid:
                issues.append(Issue("W-SELF-REFERENCE", f"{pid}: lists themselves as spouse", person.location))
            else:
                pairs.add(tuple(sorted((pid, other))))
        for marriage in person.marriages:
            other = marriage.with_id
            if other not in people:
                dangling(pid, "marriages.with", other)
            elif other == pid:
                issues.append(Issue("W-SELF-REFERENCE", f"{pid}: marriage with themselves", person.location))
            else:
                key = tuple(sorted((pid, other)))
                pairs.add(key)
                event = Event(date=marriage.date, place=marriage.place)
                entries = marriage_entries.setdefault(key, [])
                if event not in entries:
                    entries.append(event)

    couples: dict[str, Couple] = {}
    birth_couple: dict[str, str] = {}
    for child in sorted(declared):
        if not declared[child]:
            continue
        cid = couple_id(declared[child])
        couples.setdefault(cid, Couple(cid, sorted(declared[child])))
        birth_couple[child] = cid
    for key in sorted(pairs):
        cid = couple_id(list(key))
        couples.setdefault(cid, Couple(cid, list(key)))
    for key, events in sorted(marriage_entries.items()):
        cid = couple_id(list(key))
        couples[cid].marriage = events[0]
        if len(events) > 1:
            issues.append(
                Issue("W-MARRIAGE-CONFLICT", f"{' and '.join(key)}: differing marriage entries; using the first")
            )

    kids: dict[str, list[str]] = {cid: [] for cid in couples}
    for child, cid in birth_couple.items():
        kids[cid].append(child)
    for cid in kids:
        kids[cid].sort()
    couples_of: dict[str, list[str]] = {pid: [] for pid in people}
    for cid, couple in couples.items():
        for pid in couple.partners:
            couples_of[pid].append(cid)
    for pid in couples_of:
        couples_of[pid].sort()

    return Relations(
        parents=declared,
        birth_couple=birth_couple,
        couples=couples,
        kids=kids,
        couples_of=couples_of,
        issues=issues,
    )
