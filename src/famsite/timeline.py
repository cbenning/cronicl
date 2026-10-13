from __future__ import annotations

from .dates import parse_date
from .model import Tree
from .relations import Relations

_TYPE_ORDER = {"birth": 0, "marriage": 1, "partnership": 1, "divorce": 2, "death": 3}


def _event(event_id: str, kind: str, date_text: str | None, place: str | None, people: list[str]) -> dict | None:
    parsed = parse_date(date_text)
    if parsed is None:
        return None
    return {
        "id": event_id,
        "type": kind,
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "date": date_text,
        "approx": parsed.approx,
        "place": place or "",
        "people": people,
    }


def build_timeline(tree: Tree, relations: Relations) -> dict:
    """Dated life events (birth, marriage, death) plus the relationships needed for per-person timelines."""
    events: list[dict] = []
    for pid in sorted(tree.people):
        person = tree.people[pid]
        if person.birth:
            e = _event(f"birth:{pid}", "birth", person.birth.date, person.birth.place, [pid])
            if e:
                events.append(e)
        if person.death:
            e = _event(f"death:{pid}", "death", person.death.date, person.death.place, [pid])
            if e:
                events.append(e)
    for cid in sorted(relations.couples):
        couple = relations.couples[cid]
        if len(couple.partners) < 2:
            continue
        for index, entry in enumerate(couple.partnerships):
            suffix = f":{index}" if index else ""
            kind = "marriage" if entry.type == "marriage" else "partnership"
            start = _event(f"{kind}:{cid}{suffix}", kind, entry.start, entry.place, list(couple.partners))
            if start:
                start["kind"] = entry.type or "unknown"
                events.append(start)
            end = _event(f"divorce:{cid}{suffix}", "divorce", entry.end, None, list(couple.partners))
            if end:
                end["kind"] = entry.type or "unknown"
                end["reason"] = entry.end_reason or ""
                events.append(end)

    events.sort(
        key=lambda e: (e["year"], e["month"] or 0, e["day"] or 0, _TYPE_ORDER[e["type"]], e["id"]),
    )

    dated: set[str] = {pid for e in events for pid in e["people"]}
    people: dict[str, dict] = {}
    for pid in sorted(tree.people):
        spouses: list[str] = []
        children: list[str] = []
        for cid in relations.couples_of.get(pid, []):
            spouses += [x for x in relations.couples[cid].partners if x != pid]
            children += relations.kids.get(cid, [])
        parents = list(relations.parents.get(pid, []))
        siblings = sorted(
            {
                other
                for parent in parents
                for cid in relations.couples_of.get(parent, [])
                for other in relations.kids.get(cid, [])
                if other != pid
            }
        )
        people[pid] = {
            "name": tree.people[pid].display_name,
            "parents": parents,
            "spouses": sorted(set(spouses)),
            "children": sorted(set(children)),
            "siblings": siblings,
        }

    years = [e["year"] for e in events]
    return {
        "version": 1,
        "range": {"min": min(years) if years else None, "max": max(years) if years else None},
        "events": events,
        "people": people,
        "undated": sorted(pid for pid in tree.people if pid not in dated),
    }
