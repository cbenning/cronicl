"""Generation numbering for a family, and the check that one exists (shared by layout and `check`)."""
from __future__ import annotations

from .model import Tree
from .relations import build_relations  # noqa: F401  (used by _couples_and_kids)

class LayoutError(Exception):
    """The tree cannot be laid out (for example, it contains an ancestry cycle)."""


def _sibling_groups(unions, kids) -> dict[str, list[str]]:
    """For every person, all their children across couples: full and half siblings share a row."""
    by_parent: dict[str, set[str]] = {}
    for uid, members in unions.items():
        for pid in members:
            by_parent.setdefault(pid, set()).update(kids[uid])
    return {pid: sorted(children) for pid, children in sorted(by_parent.items()) if len(children) > 1}


def _generation_pass(gen, unions, kids, siblings) -> set[str]:
    """One relaxation pass; returns the couples (or sibling groups) that moved."""
    moved: set[str] = set()
    for uid in sorted(unions):
        members = unions[uid]
        row = max(gen[p] for p in members)
        for pid in members:
            if gen[pid] != row:
                gen[pid] = row
                moved.add(uid)
        for kid in kids[uid]:
            if gen[kid] < row + 1:
                gen[kid] = row + 1
                moved.add(uid)
    for parent, children in siblings.items():
        deepest = max(gen[c] for c in children)
        for child in children:
            if gen[child] != deepest:
                gen[child] = deepest
                moved.add(f"children of {parent}")
    return moved


def _settle(people, unions, kids, siblings) -> tuple[dict[str, int] | None, set[str]]:
    """Generation rows with the given sibling groups; (None, the couples that kept moving) when they never settle."""
    gen = {pid: 0 for pid in people}
    for _ in range(len(people) + len(unions) + 2):
        if not _generation_pass(gen, unions, kids, siblings):
            return gen, set()
    involved: set[str] = set()
    for _ in range(len(unions) + 2):
        involved |= _generation_pass(gen, unions, kids, siblings)
    return None, involved


def _generations(people, unions, kids) -> dict[str, int]:
    """Row numbers: spouses share a row, children sit below their parents, and siblings share a row when they can.

    A marriage inside the family (an uncle and a niece) cannot also keep every sibling group on one row, so when the
    strict rules never settle the sibling rule is given up and the people are drawn by their couples and parents alone.
    A person marrying their own ancestor or descendant still cannot be drawn and is reported.
    """
    gen, involved = _settle(people, unions, kids, _sibling_groups(unions, kids))
    if gen is not None:
        return gen
    relaxed, _ = _settle(people, unions, kids, {})
    if relaxed is not None:
        return relaxed
    raise LayoutError(
        "could not assign generations: spouses must share a row but their ancestry puts them in different "
        "generations (or the tree has an ancestry cycle); couples involved: " + ", ".join(sorted(involved))
    )


def _couples_and_kids(tree: Tree):
    relations = build_relations(tree)
    unions = {cid: list(couple.partners) for cid, couple in sorted(relations.couples.items())}
    kids = {cid: list(relations.kids.get(cid, [])) for cid in unions}
    return relations, unions, kids


def generation_conflict(tree: Tree) -> str | None:
    """Return a description of why generations cannot be assigned, or None if they can."""
    _, unions, kids = _couples_and_kids(tree)
    try:
        _generations(sorted(tree.people), unions, kids)
    except LayoutError as exc:
        return str(exc)
    return None


