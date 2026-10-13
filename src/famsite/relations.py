from __future__ import annotations

from dataclasses import dataclass, field

from .issues import Issue
from .model import Event, Partnership, Tree


@dataclass
class CouplePartnership:
    """One merged partnership of a couple, as declared across both partners' files."""

    type: str = "unknown"
    start: str | None = None
    end: str | None = None
    end_reason: str | None = None
    place: str | None = None
    note: str | None = None


@dataclass
class Couple:
    id: str
    partners: list[str]
    partnerships: list[CouplePartnership] = field(default_factory=list)

    @property
    def ended(self) -> bool:
        return bool(self.partnerships) and self.partnerships[-1].end is not None

    @property
    def marriage(self) -> Event | None:
        """Transitional: the first marriage with a date or place. Removed once timeline/render read partnerships."""
        for entry in self.partnerships:
            if entry.type == "marriage" and (entry.start or entry.place):
                return Event(date=entry.start, place=entry.place)
        return None


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


_VAGUE_TYPES = (None, "unknown")
_MERGED_FIELDS = ("start", "end", "end_reason", "place", "note")


def _same_partnership(group: CouplePartnership, entry: Partnership) -> bool:
    types_agree = group.type == "unknown" or entry.type in _VAGUE_TYPES or group.type == entry.type
    starts_agree = group.start is None or entry.start is None or group.start == entry.start
    return types_agree and starts_agree


def _merge(group: CouplePartnership, entry: Partnership, pair: tuple[str, ...], issues: list[Issue]) -> None:
    if group.type == "unknown" and entry.type not in _VAGUE_TYPES:
        group.type = entry.type
    for name in _MERGED_FIELDS:
        value = getattr(entry, name)
        if value is None:
            continue
        current = getattr(group, name)
        if current is None:
            setattr(group, name, value)
        elif current != value:
            issues.append(
                Issue(
                    "W-PARTNERSHIP-CONFLICT",
                    f"{' and '.join(pair)}: differing {name} ({current!r} vs {value!r}); using the first",
                )
            )


def _start_key(group: CouplePartnership) -> tuple[bool, str]:
    return (group.start is None, (group.start or "").lstrip("~"))


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
    merged: dict[tuple[str, ...], list[CouplePartnership]] = {}
    for pid in sorted(people):
        person = people[pid]
        for other in person.spouse:
            if other not in people:
                dangling(pid, "spouse", other)
            elif other == pid:
                issues.append(Issue("W-SELF-REFERENCE", f"{pid}: lists themselves as spouse", person.location))
            else:
                pairs.add(tuple(sorted((pid, other))))
        for marriage in person.partnerships:
            other = marriage.with_id
            if not other:
                issues.append(
                    Issue("W-PARTNERSHIP-NO-PARTNER", f"{pid}: partnership entry names no partner (with:)", person.location)
                )
            elif other not in people:
                dangling(pid, "partnerships.with", other)
            elif other == pid:
                issues.append(Issue("W-SELF-REFERENCE", f"{pid}: partnership with themselves", person.location))
            else:
                key = tuple(sorted((pid, other)))
                pairs.add(key)
                groups = merged.setdefault(key, [])
                for group in groups:
                    if _same_partnership(group, marriage):
                        _merge(group, marriage, key, issues)
                        break
                else:
                    groups.append(
                        CouplePartnership(
                            type=marriage.type or "unknown",
                            start=marriage.start,
                            end=marriage.end,
                            end_reason=marriage.end_reason,
                            place=marriage.place,
                            note=marriage.note,
                        )
                    )

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
    for key, groups in sorted(merged.items()):
        couples[couple_id(list(key))].partnerships = sorted(groups, key=_start_key)

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
