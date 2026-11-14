from __future__ import annotations

from .dates import date_year
from .model import Tree
from .relations import Relations


def _descendants(relations: Relations, pid: str) -> int:
    seen: set[str] = set()
    stack = [pid]
    while stack:
        current = stack.pop()
        for cid in relations.couples_of.get(current, []):
            for kid in relations.kids.get(cid, []):
                if kid not in seen and kid != pid:
                    seen.add(kid)
                    stack.append(kid)
    return len(seen)


def home_person(tree: Tree, relations: Relations) -> str | None:
    """The person the tree opens on: `home:` in site.yml when it names someone, else the person with the most
    descendants (ties: earliest birth year, people with none last, then id)."""
    configured = (tree.site or {}).get("home")
    if configured and str(configured) in tree.people:
        return str(configured)
    if not tree.people:
        return None

    def key(pid: str):
        person = tree.people[pid]
        year = date_year(person.birth.date) if person.birth else None
        return (-_descendants(relations, pid), year is None, year or 0, pid)

    return min(tree.people, key=key)
