from __future__ import annotations

from .dates import date_year, format_years
from .model import Tree
from .relations import Relations


def _node(tree: Tree, pid: str) -> dict:
    person = tree.people[pid]
    return {
        "id": pid,
        "name": person.display_name,
        "years": format_years(person.birth.date if person.birth else None, person.death.date if person.death else None),
    }


def ancestor_tree(tree: Tree, relations: Relations, pid: str, generations: int = 4) -> dict | None:
    """The person and their recorded ancestors, at most `generations` levels deep; None when no parent is recorded.

    Only people who are recorded are drawn, and a person who is their own ancestor (a data error) ends the branch.
    """
    if not relations.parents.get(pid):
        return None

    def build(current: str, level: int, path: frozenset[str]) -> dict:
        node = _node(tree, current)
        node["parents"] = []
        if level < generations:
            for parent in relations.parents.get(current, []):
                if parent not in path and parent in tree.people:
                    node["parents"].append(build(parent, level + 1, path | {current}))
        return node

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


def count_descendants(outline: list[dict]) -> int:
    return sum(1 + count_descendants(node["children"]) for node in outline)
