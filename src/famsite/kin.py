from __future__ import annotations

from .model import Tree
from .relations import Relations


def build_kin(tree: Tree, relations: Relations) -> dict:
    """The parent and partner graph the browser needs to work out kinship, from the (redacted) tree."""
    people: dict[str, dict] = {}
    for pid in sorted(tree.people):
        person = tree.people[pid]
        partners = sorted(
            {
                other
                for cid in relations.couples_of.get(pid, [])
                if len(relations.couples[cid].partners) == 2
                for other in relations.couples[cid].partners
                if other != pid
            }
        )
        people[pid] = {
            "name": person.display_name,
            "sex": person.sex if person.sex in ("M", "F") else "U",
            "parents": list(relations.parents.get(pid, [])),
            "partners": partners,
        }
    return {"people": people}
