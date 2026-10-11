from __future__ import annotations

from .dates import parse_date
from .issues import Issue
from .model import Person, Tree
from .relations import build_relations
from .slug import is_valid_id


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


def _check_date(value: str | None, label: str, person: Person, out: list[Issue]) -> None:
    if value and parse_date(value) is None:
        out.append(
            Issue("W-DATE-UNPARSED", f"{person.id}: {label} date {value!r} is not a recognised date", person.location)
        )


def _cycle_members(parents: dict[str, list[str]]) -> set[str]:
    state: dict[str, int] = {}
    bad: set[str] = set()
    for start in sorted(parents):
        if state.get(start):
            continue
        state[start] = 1
        stack = [(start, iter(parents[start]))]
        while stack:
            node, children = stack[-1]
            for nxt in children:
                seen = state.get(nxt, 0)
                if seen == 1:
                    bad.add(nxt)
                elif seen == 0:
                    state[nxt] = 1
                    stack.append((nxt, iter(parents.get(nxt, []))))
                    break
            else:
                state[node] = 2
                stack.pop()
    return bad


def check_tree(tree: Tree, load_issues: list[Issue] | None = None) -> list[Issue]:
    issues: list[Issue] = list(load_issues or [])
    relations = build_relations(tree)
    issues += relations.issues

    for person in tree.people.values():
        where = person.location
        if not is_valid_id(person.id):
            issues.append(Issue("E-INVALID-ID", f"person id {person.id!r} is not a valid id", where))
        if person.path is not None and person.path.name != f"{person.id}.md":
            issues.append(Issue("W-FILENAME-DRIFT", f"file name does not match id {person.id!r}; run fix", where))
        if not (person.given or person.surname):
            issues.append(Issue("W-NO-NAME", f"{person.id}: person has no name", where))
        if person.sex not in ("M", "F", "U"):
            issues.append(Issue("W-BAD-SEX", f"{person.id}: sex {person.sex!r} is not M, F or U", where))
        if person.birth:
            _check_date(person.birth.date, "birth", person, issues)
        if person.death:
            _check_date(person.death.date, "death", person, issues)
        for marriage in person.marriages:
            _check_date(marriage.date, "marriage", person, issues)

    for pid in sorted(_cycle_members(relations.parents)):
        issues.append(Issue("E-CYCLE", f"{pid}: person is their own ancestor", tree.people[pid].location))

    return sorted(issues, key=lambda i: (i.path or "", i.code, i.message))
