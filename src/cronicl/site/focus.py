from __future__ import annotations

import dataclasses

from ..core.model import Tree
from ..core.relations import Relations


def focus_people(tree: Tree, relations: Relations, pid: str) -> set[str]:
    """The person, everyone above them, everyone below them, and the spouses of the person and their descendants.

    Siblings, aunts, uncles, cousins and step-relations are deliberately left out.
    """
    ancestors: set[str] = set()
    stack = list(relations.parents.get(pid, []))
    while stack:
        current = stack.pop()
        if current in ancestors or current == pid:
            continue
        ancestors.add(current)
        stack.extend(relations.parents.get(current, []))

    descendants: set[str] = set()
    stack = [pid]
    while stack:
        current = stack.pop()
        for cid in relations.couples_of.get(current, []):
            for child in relations.kids.get(cid, []):
                if child not in descendants and child != pid:
                    descendants.add(child)
                    stack.append(child)

    spouses: set[str] = set()
    for member in {pid} | descendants:
        for cid in relations.couples_of.get(member, []):
            spouses.update(relations.couples[cid].partners)
    return ancestors | descendants | spouses | {pid}


def hidden_counts(relations: Relations, keep: set[str]) -> dict[str, int]:
    """For each kept person, how many parents, partners, children and siblings a focused tree leaves out.

    Only counts above zero are returned.
    """
    counts: dict[str, int] = {}
    for pid in keep:
        kin = set(relations.parents.get(pid, []))
        for cid in relations.couples_of.get(pid, []):
            kin.update(relations.couples[cid].partners)
            kin.update(relations.kids.get(cid, []))
        for parent in relations.parents.get(pid, []):
            for cid in relations.couples_of.get(parent, []):
                kin.update(relations.kids.get(cid, []))
        kin.discard(pid)
        missing = len(kin - keep)
        if missing:
            counts[pid] = missing
    return counts


def focus_tree(tree: Tree, relations: Relations, pid: str) -> Tree:
    """A copy of the tree restricted to the focus set, with relationships rebuilt from the derived couples."""
    keep = focus_people(tree, relations, pid)
    people = {}
    for person_id in sorted(keep):
        person = tree.people[person_id]
        spouses = sorted(
            {
                other
                for cid in relations.couples_of.get(person_id, [])
                for other in relations.couples[cid].partners
                if other != person_id and other in keep
            }
        )
        people[person_id] = dataclasses.replace(
            person,
            parents=[p for p in relations.parents.get(person_id, []) if p in keep],
            spouse=spouses,
            children=[],
            partnerships=[dataclasses.replace(p) for p in person.partnerships if p.with_id in keep],
            path=None,
        )
    return Tree(people=people, site=dict(tree.site))
