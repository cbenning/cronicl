from __future__ import annotations

from ..core.dates import date_year, format_years
from ..core.model import Tree
from ..core.relations import Relations


def _node(tree: Tree, pid: str) -> dict:
    person = tree.people[pid]
    return {
        "id": pid,
        "name": person.display_name,
        "years": format_years(person.birth.date if person.birth else None, person.death.date if person.death else None),
    }


MAX_GENERATIONS = 12  # a safety stop for very deep (or very tangled) files; real trees end long before


def ancestor_outline(tree: Tree, relations: Relations, pid: str, generations: int = MAX_GENERATIONS) -> list[dict]:
    """The person's parents, their parents and so on, in the same shape as `descendant_outline` (nested under "children").

    Only people who are recorded appear, and a person who is their own ancestor (a data error) ends the branch.
    """

    def build(current: str, level: int, path: frozenset[str]) -> list[dict]:
        out = []
        if level > generations:
            return out
        for parent in relations.parents.get(current, []):
            if parent in path or parent == current or parent not in tree.people:
                continue
            node = _node(tree, parent)
            node["children"] = build(parent, level + 1, path | {current})
            out.append(node)
        return out

    return build(pid, 1, frozenset())


def descendant_outline(tree: Tree, relations: Relations, pid: str) -> list[dict]:
    """The person's children, their children and so on, each level ordered by birth year (unknown last)."""

    def build(current: str, path: frozenset[str]) -> list[dict]:
        kids: list[str] = []
        for cid in relations.couples_of.get(current, []):
            kids += relations.kids.get(cid, [])

        def key(kid: str):
            person = tree.people[kid]
            year = date_year(person.birth.date) if person.birth else None
            return (year is None, year or 0, person.display_name.lower(), kid)

        out = []
        for kid in sorted(set(kids), key=key):
            if kid in path or kid == current:
                continue
            node = _node(tree, kid)
            node["children"] = build(kid, path | {current})
            out.append(node)
        return out

    return build(pid, frozenset())


def count_people(outline: list[dict]) -> int:
    return sum(1 + count_people(node["children"]) for node in outline)
