from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .issues import Issue
from .model import Marriage
from .slug import FALLBACK_SLUG, is_valid_id, natural_key, slugify, unique_id
from .store import dump_person, read_records


@dataclass
class FixPlan:
    writes: dict[Path, str] = field(default_factory=dict)
    deletes: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unresolved: list[Issue] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.writes or self.deletes)


def _rel(path: Path, data_dir: Path) -> str:
    try:
        return path.relative_to(data_dir).as_posix()
    except ValueError:
        return str(path)


def plan_fix(data_dir: Path) -> FixPlan:
    data_dir = Path(data_dir)
    people, load_issues = read_records(data_dir)
    plan = FixPlan()
    plan.unresolved += [i for i in load_issues if i.code == "E-BAD-FRONTMATTER"]

    explicit_counts = Counter(p.id for p in people if p.id_pinned)
    taken: set[str] = set()
    final: dict[int, str] = {}
    aliases: dict[str, str] = {}
    skipped: set[int] = set()

    for index, person in enumerate(people):
        if person.id_pinned and is_valid_id(person.id):
            final[index] = person.id
            taken.add(person.id)
            if explicit_counts[person.id] > 1:
                skipped.add(index)
                plan.unresolved.append(
                    Issue(
                        "E-DUPLICATE-ID",
                        f"id {person.id!r} is used by more than one file; resolve by hand",
                        _rel(person.path, data_dir),
                    )
                )

    pending = [i for i in range(len(people)) if i not in final]
    pending.sort(key=lambda i: (natural_key(people[i].gedcom_id or ""), str(people[i].path)))
    for index in pending:
        person = people[index]
        base = slugify(person.id) or FALLBACK_SLUG
        new_id = unique_id(base, taken)
        taken.add(new_id)
        final[index] = new_id
        aliases.setdefault(person.id, new_id)
        if not person.id_pinned:
            aliases.setdefault(person.path.stem, new_id)

    valid = set(final.values())

    def ref(value: str) -> str:
        if value in valid:
            return value
        return aliases.get(value, value)

    for index, person in enumerate(people):
        if index in skipped:
            continue
        updated = dataclasses.replace(
            person,
            id=final[index],
            parents=[ref(x) for x in person.parents],
            spouse=[ref(x) for x in person.spouse],
            children=[ref(x) for x in person.children],
            marriages=[Marriage(ref(m.with_id), m.date, m.place) for m in person.marriages],
            id_pinned=True,
        )
        content = dump_person(updated)
        old_path = person.path
        new_path = data_dir / "people" / f"{updated.id}.md"
        if new_path != old_path:
            plan.writes[new_path] = content
            plan.deletes.append(old_path)
            plan.notes.append(f"rename {_rel(old_path, data_dir)} -> {_rel(new_path, data_dir)}")
        elif old_path.read_text(encoding="utf-8") != content:
            plan.writes[old_path] = content
            plan.notes.append(f"normalize {_rel(old_path, data_dir)}")
    return plan


def apply_plan(plan: FixPlan) -> None:
    for path, content in plan.writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for path in plan.deletes:
        if path not in plan.writes and path.exists():
            path.unlink()
