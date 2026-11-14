from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

import jinja2
from markdown_it import MarkdownIt

from .dates import age_between, date_year, format_date, format_years, parse_date
from .facts import fact_label
from .focus import focus_people, focus_tree, hidden_counts
from .home import home_person
from .kin import build_kin
from .layout import compute_layout
from .lineage import ancestor_tree, count_descendants, descendant_outline
from .links import page_links
from .media import ALLOWED, resolve
from .model import Event, Tree
from .places import place_index
from .privacy import is_living, redact
from .relations import Relations, build_relations
from .slug import slugify
from .stats import site_stats
from .store import cites_of
from .timeline import build_timeline, event_text

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
    return {"date": event.date, "place": event.place, "when": format_date(event.date)}


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
        text += f" {format_date(start)}"
    if end:
        text += " – " + _END_WORD.get(end_reason, "ended")
        if end != "unknown":
            text += f" {format_date(end)}"
    if place:
        text += f" ({place})"
    return text


def _partnership(entry) -> dict:
    return {
        "type": entry.type, "start": entry.start, "end": entry.end, "end_reason": entry.end_reason,
        "place": entry.place, "note": entry.note,
        "text": partnership_text(entry.type, entry.start, entry.end, entry.end_reason, entry.place),
    }


def _event_origin(tree: Tree, source: dict) -> tuple[str | None, list[str]]:
    """The note and citations written on the entry a timeline event came from."""
    kind, _, rest = source["id"].partition(":")
    pid, _, index = rest.partition(":")
    person = tree.people.get(pid)
    if person is None:
        return None, []
    if kind in ("birth", "death"):
        event = person.birth if kind == "birth" else person.death
        extra = event.extra if event else {}
        note = extra.get("note")
        return (note.strip() or None if isinstance(note, str) else None), cites_of(extra.get("cite"))
    if kind == "fact" and index.isdigit() and int(index) < len(person.events):
        entry = person.events[int(index)]
        return entry.note, list(entry.cite)
    return None, []


def life_summary(payload: dict) -> str:
    """One or two sentences about a life, in words: "Born 12 March 1941 in Guelph. Died 2021, aged 80." """

    def clause(word: str, event: dict | None) -> str:
        if not event or not (event.get("when") or event.get("place")):
            return ""
        text = word
        if event.get("when"):
            text += f" {event['when']}"
        if event.get("place"):
            text += f" in {event['place']}"
        return text

    born = clause("Born", payload.get("birth"))
    died = clause("Died", payload.get("death"))
    if died and payload.get("age_at_death") is not None:
        died += ", aged " + ("about " if payload.get("age_at_death_approx") else "") + str(payload["age_at_death"])
    return " ".join(f"{part}." for part in (born, died) if part)


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
        entry["when"] = format_date(source["date"])
        if source.get("end"):
            entry["when"] += " – " + format_date(source["end"])
        note, cite = _event_origin(tree, source) if row["role"] == "self" else (None, [])
        entry["note"], entry["cite"] = note, cite
        entry.update(role=row["role"], text=row["text"], age=row["age"], age_approx=row["age_approx"])
        events.append(entry)
    facts = [
        {
            "label": fact_label(entry.type),
            "text": entry.value or entry.place or entry.date or entry.start or "",
            "note": entry.note,
            "cite": list(entry.cite),
        }
        for entry in person.events
        if parse_date(entry.date or entry.start) is None
    ]
    payload = {
        "id": pid,
        "name": person.display_name,
        "sex": person.sex,
        "years": format_years(birth_date, death_date),
        "summary": "",
        "birth": _event(person.birth),
        "death": _event(person.death),
        "bodyHtml": _markdown.render(person.body) if person.body.strip() else "",
        "initials": person.initials,
        "image": None,
        "age_at_death": age,
        "age_at_death_approx": bool(age is not None and (born.approx or died.approx)),
        "siblings": _siblings(tree, rel, pid),
        "events": events,
        "facts": facts,
        "parents": parents,
        "spouses": spouses,
        "children": children,
    }
    payload["summary"] = life_summary(payload)
    return payload


def _asset_version(name: str) -> str:
    """A short content hash for a viewer asset, so a rebuilt viewer is never served from a browser's cache."""
    return hashlib.sha256((_PACKAGE / "viewer" / name).read_bytes()).hexdigest()[:12]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_GENERATED_DIRS = ("data", "p", "focus", "people", "places", "relate", "media", "tree", "timeline")
_GENERATED_FILES = ("index.html", "tree.html", "layout.json", "index.json", "timeline.json", "viewer.js", "style.css", "site.js", "kin.js", "kin.json")


def _clear_generated(out_dir: Path) -> None:
    """Remove what a previous build wrote, so a person who became private cannot linger in the output."""
    for name in _GENERATED_DIRS:
        shutil.rmtree(out_dir / name, ignore_errors=True)
    for name in _GENERATED_FILES:
        (out_dir / name).unlink(missing_ok=True)


def _portraits(visible: Tree, out_dir: Path, media_dir: Path | None) -> dict[str, dict]:
    """Copy each referenced portrait, once, into out/media/ and return the payload `image` for each person.

    Only people in the redacted tree are considered, so a living person's file is never read or copied. A path that
    leaves media/, a missing file or a type that is not allowed is skipped (`check` reports it).
    """
    images: dict[str, dict] = {}
    if media_dir is None:
        return images
    for pid in sorted(visible.people):
        person = visible.people[pid]
        if not person.portrait or not person.portrait.lower().endswith(ALLOWED):
            continue
        source = resolve(media_dir, person.portrait)
        if source is None:
            continue
        target = out_dir / "media" / person.portrait
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        images[pid] = {"src": "media/" + quote(person.portrait), "alt": f"Portrait of {person.display_name}"}
    return images


def _home_context(visible: Tree, site: dict, payloads: dict, timeline: dict, relations: Relations, home: str,
                  recent: list[dict] | None) -> dict:
    """Everything the home page prints, derived from the redacted tree."""
    names = {pid: person.display_name for pid, person in visible.people.items()}
    intro = str(site.get("intro", "") or "").strip()
    on_this_day = sorted(
        (
            {
                "md": f"{e['month']:02d}-{e['day']:02d}",
                "year": e["year"],
                "text": event_text(e, names, None),
                "id": e["people"][0],
            }
            for e in timeline["events"]
            if e["month"] and e["day"]
        ),
        key=lambda item: (item["md"], item["year"], item["id"]),
    )
    changed = [
        {**_ref(visible, item["id"]), "when": format_date(item["date"])}
        for item in (recent or [])
        if item["id"] in visible.people
    ]
    return {
        "intro_html": _markdown.render(intro) if intro else "",
        "home_ref": _ref(visible, home) if home else None,
        "stats": site_stats(visible, relations, timeline),
        "recent": changed,
        "on_this_day": on_this_day,
    }


def _people_groups(visible: Tree, index: list[dict]) -> list[dict]:
    """People grouped by surname (case and accents folded), groups in folded order, nameless people last."""
    by_slug: dict[str, dict] = {}
    for entry in index:  # `index` is sorted by name then id
        surname = (visible.people[entry["id"]].surname or "").strip()
        slug = slugify(surname) or "none"
        group = by_slug.setdefault(slug, {"slug": slug, "heading": surname or "No surname recorded", "people": []})
        group["people"].append(entry)
    for group in by_slug.values():
        if group["slug"] != "none":
            first = min(group["people"], key=lambda e: e["id"])
            group["heading"] = (visible.people[first["id"]].surname or "").strip()
    ordered = sorted(by_slug.values(), key=lambda g: (g["slug"] == "none", g["slug"]))
    return ordered


def build_site(
    tree: Tree, out_dir: Path, *, today: date, recent: list[dict] | None = None, media_dir: Path | None = None
) -> BuildSummary:
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
    home = home_person(visible, relations) or ""

    cutoff = int(privacy.get("cutoff_years", 100))
    living = {pid for pid, person in visible.people.items() if is_living(person, today, cutoff)}
    timeline = build_timeline(visible, relations, living)
    payloads = {pid: person_payload(visible, pid, relations, timeline) for pid in sorted(visible.people)}
    images = _portraits(visible, out_dir, media_dir)
    for pid, payload in payloads.items():
        payload["image"] = images.get(pid)
    index = sorted(
        (
            {"id": pid, "name": pl["name"], "years": pl["years"], "image": pl["image"]["src"] if pl["image"] else None}
            for pid, pl in payloads.items()
        ),
        key=lambda e: (e["name"].lower(), e["id"]),
    )

    written = len({image["src"] for image in images.values()})

    def put(rel: str, text: str) -> None:
        nonlocal written
        _write(out_dir / rel, text)
        written += 1

    env = _env()
    put("layout.json", dumps(layout))
    put("index.json", dumps(index))
    put("kin.json", dumps(build_kin(visible, relations)))
    # Each person's own event rows live in data/people/<id>.json; repeating them here would grow this file with the
    # number of people squared-ish, and the Timeline tab downloads it whole.
    public_timeline = {
        **timeline,
        "people": {pid: {k: v for k, v in info.items() if k != "events"} for pid, info in timeline["people"].items()},
    }
    put("timeline.json", dumps(public_timeline))
    versions = {"js": _asset_version("viewer.js"), "css": _asset_version("style.css"), "site": _asset_version("site.js"), "kin": _asset_version("kin.js")}
    home_context = _home_context(visible, tree.site, payloads, timeline, relations, home, recent)
    put("index.html", env.get_template("home.html").render(title=title, v=versions, home=home, root="", active="home", **home_context))
    put(
        "people/index.html",
        env.get_template("people.html").render(
            title=title, v=versions, home=home, root="../", active="people", groups=_people_groups(visible, index)
        ),
    )
    places = [
        {
            **place,
            "entries": [
                {**entry, "name": visible.people[entry["id"]].display_name, "when": format_date(entry["date"])}
                for entry in place["entries"]
            ],
        }
        for place in place_index(visible, relations)
    ]
    put(
        "places/index.html",
        env.get_template("places.html").render(title=title, v=versions, home=home, root="../", active="places", places=places),
    )
    put(
        "relate/index.html",
        env.get_template("relate.html").render(title=title, v=versions, home=home, root="../", people=index),
    )
    for page in ("tree", "timeline"):
        put(
            f"{page}/index.html",
            env.get_template("viewer.html").render(
                title=title, people=index, v=versions, home=home, root="../", page=page, active=page
            ),
        )
    put("tree.html", env.get_template("tree_forward.html").render(title=title))
    person_template = env.get_template("person.html")
    for pid in sorted(visible.people):
        focused = compute_layout(focus_tree(visible, relations, pid))
        focused["focus"] = pid
        focused["hidden"] = hidden_counts(relations, focus_people(visible, relations, pid))
        put(f"focus/{pid}.json", dumps(focused))
    for pid, payload in payloads.items():
        put(f"data/people/{pid}.json", dumps(payload))
        outline = descendant_outline(visible, relations, pid)
        put(
            f"p/{pid}/index.html",
            person_template.render(
                title=title, person=payload, ancestors=ancestor_tree(visible, relations, pid),
                descendants=outline, descendant_count=count_descendants(outline),
                links=page_links(tree.site, pid, payload["name"]) if pid in tree.people else [],
                v=versions, home=home, root="../../"
            ),
        )

    for asset in ("viewer.js", "style.css", "site.js", "kin.js"):
        source = _PACKAGE / "viewer" / asset
        if source.exists():
            target = out_dir / asset
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written += 1
    return BuildSummary(people=len(payloads), files=written)
