"""Turn an old data folder (one markdown file per person) into family.yml, losing nothing.

The old files are moved to archive/people-md/, never deleted. The couples are built exactly the way the site merged
them (`build_relations`), so the migrated site shows the same relationships.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import emit
from .check import check_tree
from .family import has_family, partnerships_from_events
from .relations import build_relations
from .legacy import load_legacy_tree
from .store import load_site


class MigrateRefused(Exception):
    pass


@dataclass
class MigrationPlan:
    family_text: str
    gedcom_extra_text: str | None
    site_text: str | None
    notes: list[str] = field(default_factory=list)
    people: int = 0
    couples: int = 0
    events: int = 0


def _site_with_version_3(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_bytes().decode("utf-8")
    if re.search(r"(?m)^schema_version:.*$", text):
        return re.sub(r"(?m)^schema_version:.*$", "schema_version: 3", text, count=1)
    newline = "\r\n" if "\r\n" in text else "\n"
    return text + ("" if text.endswith("\n") or not text else newline) + "schema_version: 3" + newline


def plan_migration(data_dir: Path) -> MigrationPlan:
    data_dir = Path(data_dir)
    if has_family(data_dir):
        raise MigrateRefused("family.yml (or a family/ folder) already exists: this folder is already migrated")
    if not (data_dir / "people").is_dir() or not any((data_dir / "people").glob("*.md")):
        raise MigrateRefused(f"{data_dir} has no people/*.md to migrate")
    if (data_dir / "archive" / "people-md").exists():
        raise MigrateRefused("archive/people-md already exists; move it away first")
    tree, load_issues = load_legacy_tree(data_dir)
    tree.site, site_issues = load_site(data_dir)
    load_issues = site_issues + load_issues
    errors = [i for i in check_tree(tree, load_issues) if i.severity == "error"]
    if errors:
        shown = "; ".join(f"{i.code} {i.path or ''}: {i.message}" for i in errors[:5])
        raise MigrateRefused(f"the old data has {len(errors)} error(s); fix them first (cronicl check): {shown}")
    relations = build_relations(tree)
    notes = [f"{i.code}: {i.message}" for i in relations.issues]

    specs = []
    extras: list[tuple[str, str]] = []
    for pid in sorted(tree.people):
        person = tree.people[pid]
        spec = emit.spec_from_person(person)
        spec["parents"] = list(relations.parents.get(pid, []))
        if person.living is False and person.death is None:
            spec["death"] = "unknown"
        specs.append((pid, spec))
        if person.gedcom_extra:
            extras.append((pid, person.gedcom_extra))
        for entry in person.partnerships:
            if entry.extra:
                notes.append(f"{pid}: partnership with {entry.with_id or '?'} had keys that are not carried over: {', '.join(entry.extra)}")
        for event in person.events:
            if event.date and (event.start or event.end):
                notes.append(f"{pid}: an event has both date and start/end; start/end is not carried over")
            elif any(str(v).lstrip().upper().startswith(("~", "ABT", "CAL", "EST", "BEF", "AFT")) for v in (event.start, event.end) if v):
                notes.append(f"{pid}: an event span had an approximate (~) end; it is written as a plain span")

    pairs: set[tuple[str, str]] = set()
    for person in tree.people.values():
        for other in person.spouse:
            if other in tree.people and other != person.id:
                pairs.add(tuple(sorted((person.id, other))))
        for entry in person.partnerships:
            if entry.with_id in tree.people and entry.with_id != person.id:
                pairs.add(tuple(sorted((person.id, entry.with_id))))
    couples = []
    for a, b in sorted(pairs):
        couple = relations.couples[f"{a}+{b}"]
        events = emit.partnership_events(couple.partnerships)
        if events:
            kept = [(p.type or "", p.start, p.end, p.end_reason, p.place, p.note) for p in partnerships_from_events(events, b)]
            was = [
                ("partnership" if (p.type or "unknown") == "unknown" else p.type, emit.to_modern(p.start), emit.to_modern(p.end),
                 p.end_reason, p.place, p.note)
                for p in couple.partnerships
            ]
            if kept != was:
                notes.append(
                    f"{a} + {b}: the partnerships overlap or end in a way that couple events cannot keep apart; "
                    "in family.yml an ending applies to the latest open partnership"
                )
        if events or not relations.kids.get(couple.id):
            couples.append((a, b, {"events": events}))
    header = (
        "# yaml-language-server: $schema=family.schema.json\n"
        "# family.yml: migrated from people/*.md by `cronicl migrate`. The old files are in archive/people-md/."
    )
    family_text = emit.family(specs, couples, header=header)
    gedcom_text = None
    if extras:
        lines = ["# GEDCOM lines the import could not map, by person. Nothing reads this file."]
        for pid, text in extras:
            lines += emit._bio(text, indent="", key=pid)
        gedcom_text = "\n".join(lines) + "\n"
    return MigrationPlan(
        family_text=family_text,
        gedcom_extra_text=gedcom_text,
        site_text=_site_with_version_3(data_dir / "site.yml"),
        notes=notes,
        people=len(specs),
        couples=len(couples),
        events=sum(len(c[2]["events"]) for c in couples) + sum(len(s[1]["events"]) for s in specs),
    )


def apply_migration(data_dir: Path, plan: MigrationPlan) -> None:
    data_dir = Path(data_dir)
    (data_dir / "family.yml").write_text(plan.family_text, encoding="utf-8")
    from .schema import FAMILY_SCHEMA

    (data_dir / "family.schema.json").write_text(json.dumps(FAMILY_SCHEMA, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    archive = data_dir / "archive"
    archive.mkdir(exist_ok=True)
    if plan.gedcom_extra_text:
        (archive / "gedcom-extra.yml").write_text(plan.gedcom_extra_text, encoding="utf-8")
    if plan.site_text is not None:
        (data_dir / "site.yml").write_bytes(plan.site_text.encode("utf-8"))
    (data_dir / "people").rename(archive / "people-md")
