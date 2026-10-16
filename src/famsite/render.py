from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import jinja2
from markdown_it import MarkdownIt

from .dates import age_between, date_year, format_years, parse_date
from .focus import focus_tree
from .layout import compute_layout
from .model import Event, Tree
from .privacy import redact
from .relations import Relations, build_relations
from .timeline import build_timeline

_PACKAGE = Path(__file__).parent
_markdown = MarkdownIt("commonmark", {"html": False})


@dataclass
class BuildSummary:
    people: int
    files: int


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_PACKAGE / "templates")),
        autoescape=jinja2.select_autoescape(["html"]),
        keep_trailing_newline=True,
    )


def _event(event: Event | None):
    if event is None:
        return None
    return {"date": event.date, "place": event.place}


def _years_of(person) -> str:
    return format_years(person.birth.date if person.birth else None, person.death.date if person.death else None)


def _ref(tree: Tree, pid: str) -> dict:
    person = tree.people[pid]
    return {"id": pid, "name": person.display_name, "years": _years_of(person), "initials": person.initials}


def _siblings(tree: Tree, rel: Relations, pid: str) -> list[dict]:
    mine = rel.parents.get(pid, [])
    found: dict[str, dict] = {}
    for parent in mine:
        for cid in rel.couples_of.get(parent, []):
            for other in rel.kids.get(cid, []):
                if other == pid or other in found:
                    continue
                theirs = rel.parents.get(other, [])
                shared = [x for x in mine if x in theirs]
                if len(shared) == 2:
                    kind = "full"
                elif len(mine) == 2 and len(theirs) == 2:
                    kind = "half"
                else:
                    kind = "sibling"  # only one parent is known on a side: the other parent is not guessed
                via = [{"id": x, "name": tree.people[x].display_name} for x in shared]
                found[other] = {**_ref(tree, other), "type": kind, "via": via}

    def key(ref: dict):
        person = tree.people[ref["id"]]
        year = date_year(person.birth.date) if person.birth else None
        return (year is None, year or 0, ref["name"].lower(), ref["id"])

    return sorted(found.values(), key=key)


_TYPE_WORD = {
    "marriage": "Married", "civil-union": "Civil union", "partnership": "Partners",
    "engagement": "Engaged", "unknown": "Partners",
}
_END_WORD = {"divorce": "divorced", "annulment": "annulled", "separation": "separated"}


def partnership_text(type_, start, end, end_reason, place) -> str:
    """One readable line for a partnership, e.g. "Married 1975 – divorced 1990 (Surrey, BC)"."""
    if not (start or end or place) and type_ in (None, "unknown"):
        return ""
    text = _TYPE_WORD.get(type_ or "unknown", "Partners")
    if start:
        text += f" {start}"
    if end:
        text += " – " + _END_WORD.get(end_reason, "ended")
        if end != "unknown":
            text += f" {end}"
    if place:
        text += f" ({place})"
    return text


def _partnership(entry) -> dict:
    return {
        "type": entry.type, "start": entry.start, "end": entry.end, "end_reason": entry.end_reason,
        "place": entry.place, "note": entry.note,
        "text": partnership_text(entry.type, entry.start, entry.end, entry.end_reason, entry.place),
    }


def person_payload(tree: Tree, pid: str, relations: Relations | None = None, timeline: dict | None = None) -> dict:
    rel = relations or build_relations(tree)
    timeline = timeline if timeline is not None else build_timeline(tree, rel)
    person = tree.people[pid]
    parents = [_ref(tree, x) for x in rel.parents.get(pid, [])]
    spouses: list[dict] = []
    children: list[dict] = []
    for cid in rel.couples_of.get(pid, []):
        couple = rel.couples[cid]
        for other in couple.partners:
            if other != pid:
                spouses.append({**_ref(tree, other), "partnerships": [_partnership(p) for p in couple.partnerships]})
        children += [_ref(tree, c) for c in rel.kids.get(cid, [])]
    children.sort(key=lambda r: (r["name"].lower(), r["id"]))
    birth_date = person.birth.date if person.birth else None
    death_date = person.death.date if person.death else None
    born = parse_date(birth_date)
    died = parse_date(death_date)
    age = age_between(born, died) if born and died else None
    by_id = {e["id"]: e for e in timeline["events"]}
    events = []
    for row in timeline["people"][pid]["events"]:
        source = by_id[row["id"]]
        entry = {k: source[k] for k in ("id", "type", "year", "month", "day", "date", "place")}
        for optional in ("kind", "reason"):
            if source.get(optional):
                entry[optional] = source[optional]
        entry.update(role=row["role"], text=row["text"], age=row["age"], age_approx=row["age_approx"])
        events.append(entry)
    return {
        "id": pid,
        "name": person.display_name,
        "sex": person.sex,
        "years": format_years(birth_date, death_date),
        "birth": _event(person.birth),
        "death": _event(person.death),
        "bodyHtml": _markdown.render(person.body) if person.body.strip() else "",
        "initials": person.initials,
        "image": None,
        "age_at_death": age,
        "age_at_death_approx": bool(age is not None and (born.approx or died.approx)),
        "siblings": _siblings(tree, rel, pid),
        "events": events,
        "parents": parents,
        "spouses": spouses,
        "children": children,
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_GENERATED_DIRS = ("data", "p", "focus")
_GENERATED_FILES = ("index.html", "layout.json", "index.json", "timeline.json", "viewer.js", "style.css")


def _clear_generated(out_dir: Path) -> None:
    """Remove what a previous build wrote, so a person who became private cannot linger in the output."""
    for name in _GENERATED_DIRS:
        shutil.rmtree(out_dir / name, ignore_errors=True)
    for name in _GENERATED_FILES:
        (out_dir / name).unlink(missing_ok=True)


def build_site(tree: Tree, out_dir: Path, *, today: date) -> BuildSummary:
    out_dir = Path(out_dir)
    _clear_generated(out_dir)
    privacy = tree.site.get("privacy", {}) or {}
    visible = redact(
        tree,
        mode=privacy.get("living", "full"),
        today=today,
        cutoff_years=int(privacy.get("cutoff_years", 100)),
        salt=str(privacy.get("id_salt", "")),
    )
    relations = build_relations(visible)
    layout = compute_layout(visible)
    title = str(tree.site.get("title", "Family Tree"))

    timeline = build_timeline(visible, relations)
    payloads = {pid: person_payload(visible, pid, relations, timeline) for pid in sorted(visible.people)}
    index = sorted(
        ({"id": pid, "name": pl["name"], "years": pl["years"]} for pid, pl in payloads.items()),
        key=lambda e: (e["name"].lower(), e["id"]),
    )

    written = 0

    def put(rel: str, text: str) -> None:
        nonlocal written
        _write(out_dir / rel, text)
        written += 1

    env = _env()
    put("layout.json", dumps(layout))
    put("index.json", dumps(index))
    put("timeline.json", dumps(timeline))
    put("index.html", env.get_template("index.html").render(title=title, people=index))
    person_template = env.get_template("person.html")
    for pid in sorted(visible.people):
        focused = compute_layout(focus_tree(visible, relations, pid))
        focused["focus"] = pid
        put(f"focus/{pid}.json", dumps(focused))
    for pid, payload in payloads.items():
        put(f"data/people/{pid}.json", dumps(payload))
        put(
            f"p/{pid}/index.html",
            person_template.render(title=title, person=payload, gallery=None, tree_svg="", lifeline_svg=""),
        )

    for asset in ("viewer.js", "style.css"):
        source = _PACKAGE / "viewer" / asset
        if source.exists():
            target = out_dir / asset
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written += 1
    return BuildSummary(people=len(payloads), files=written)
