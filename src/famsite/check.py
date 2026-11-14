from __future__ import annotations

from .dates import parse_date
from .issues import Issue
from .layout import generation_conflict
from .links import valid_contact, valid_edit_url
from .media import ALLOWED, MAX_BYTES, resolve, safe_relative
from .model import END_REASONS, PARTNERSHIP_TYPES, Person, Tree
from .relations import build_relations
from .slug import is_valid_id


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


def _check_date(value: str | None, label: str, person: Person, out: list[Issue]) -> None:
    if value and parse_date(value) is None:
        out.append(
            Issue("W-DATE-UNPARSED", f"{person.id}: {label} date {value!r} is not a recognised date", person.location)
        )


def _check_portrait(person: Person, out: list[Issue]) -> None:
    """One issue at most, in this order: unsafe path, wrong type, missing file, oversized file."""
    value, where = person.portrait, person.location
    if not safe_relative(value):
        out.append(Issue("E-PORTRAIT-PATH", f"{person.id}: portrait {value!r} must be a path inside media/", where))
        return
    if not value.lower().endswith(ALLOWED):
        out.append(Issue("W-PORTRAIT-TYPE", f"{person.id}: portrait {value!r} is not one of {', '.join(ALLOWED)}", where))
        return
    if person.path is None:
        return
    media = person.path.parent.parent / "media"
    found = resolve(media, value)
    if found is None:
        candidate = media / value
        if candidate.exists() or candidate.is_symlink():
            out.append(Issue("E-PORTRAIT-PATH", f"{person.id}: portrait {value!r} leaves media/", where))
        else:
            out.append(Issue("W-PORTRAIT-MISSING", f"{person.id}: portrait file {value!r} is not in media/", where))
        return
    if found.stat().st_size > MAX_BYTES:
        out.append(Issue("W-PORTRAIT-LARGE", f"{person.id}: portrait {value!r} is over 1 MB; shrink it before publishing", where))


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

    for key, valid in (("edit_url", valid_edit_url), ("contact", valid_contact)):
        value = (tree.site or {}).get(key)
        if value and not valid(value):
            issues.append(
                Issue(
                    "W-BAD-LINK",
                    f"{key} {str(value)!r} is not an allowed link (edit_url needs https://... and {{id}}; contact is mailto:, http:// or https://)",
                    "site.yml",
                )
            )

    home = (tree.site or {}).get("home")
    if home and str(home) not in tree.people:
        issues.append(Issue("W-HOME-UNKNOWN", f"home {str(home)!r} is not a person id; the default home person is used", "site.yml"))

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
        if person.portrait:
            _check_portrait(person, issues)
        if person.birth:
            _check_date(person.birth.date, "birth", person, issues)
        if person.death:
            _check_date(person.death.date, "death", person, issues)
        for entry in person.events:
            label = entry.type or "event"
            if not entry.type:
                issues.append(Issue("W-EVENT-NO-TYPE", f"{person.id}: an event has no type", where))
            _check_date(entry.date, label, person, issues)
            _check_date(entry.start, f"{label} start", person, issues)
            _check_date(entry.end, f"{label} end", person, issues)
            begun, ended = parse_date(entry.start), parse_date(entry.end)
            if begun and ended and (ended.year, ended.month or 0, ended.day or 0) < (begun.year, begun.month or 0, begun.day or 0):
                issues.append(
                    Issue("W-END-BEFORE-START", f"{person.id}: {label} ends ({entry.end}) before it starts ({entry.start})", where)
                )
        for entry in person.partnerships:
            _check_date(entry.start, "partnership start", person, issues)
            if entry.end != "unknown":
                _check_date(entry.end, "partnership end", person, issues)
            if entry.type and entry.type not in PARTNERSHIP_TYPES:
                issues.append(
                    Issue(
                        "W-PARTNERSHIP-TYPE-UNKNOWN",
                        f"{person.id}: partnership type {entry.type!r} is not one of {', '.join(PARTNERSHIP_TYPES)}",
                        where,
                    )
                )
            if entry.end_reason and entry.end_reason not in END_REASONS:
                issues.append(
                    Issue(
                        "W-END-REASON-UNKNOWN",
                        f"{person.id}: end_reason {entry.end_reason!r} is not one of {', '.join(END_REASONS)}",
                        where,
                    )
                )

    for cid, couple in sorted(relations.couples.items()):
        for entry in couple.partnerships:
            start, end = parse_date(entry.start), parse_date(entry.end)
            if start and end and (end.year, end.month or 0, end.day or 0) < (start.year, start.month or 0, start.day or 0):
                issues.append(
                    Issue(
                        "W-END-BEFORE-START",
                        f"{cid}: partnership ends ({entry.end}) before it starts ({entry.start})",
                        tree.people[couple.partners[0]].location,
                    )
                )

    cycle_members = _cycle_members(relations.parents)
    for pid in sorted(cycle_members):
        issues.append(Issue("E-CYCLE", f"{pid}: person is their own ancestor", tree.people[pid].location))
    if not cycle_members:
        conflict = generation_conflict(tree)
        if conflict:
            issues.append(Issue("E-GENERATION-CONFLICT", conflict))

    return sorted(issues, key=lambda i: (i.path or "", i.code, i.message))
