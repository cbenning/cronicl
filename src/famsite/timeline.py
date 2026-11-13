from __future__ import annotations

from .dates import ParsedDate, age_between, parse_date, year_position
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


def event_text(event: dict, names: dict[str, str], focus: str | None = None) -> str:
    """Wording of one event; `focus` is the person whose point of view it is told from, or None for the family view."""
    people = event["people"]
    shown = [names.get(p, p) for p in people]
    joined = " & ".join(shown)
    own = focus is not None and focus in people
    others = " & ".join(names.get(p, p) for p in people if p != focus)
    kind, reason, etype = event.get("kind"), event.get("reason"), event["type"]
    if etype == "marriage":
        return f"married {others}" if own else f"{joined} married"
    if etype == "partnership":
        if kind == "engagement":
            return f"engaged to {others}" if own else f"{joined} engaged"
        if kind == "civil-union":
            return f"entered a civil union with {others}" if own else f"{joined} entered a civil union"
        return f"became partners with {others}" if own else f"{joined} became partners"
    if etype == "divorce":
        noun = "Marriage" if kind == "marriage" else "Partnership"
        if reason == "divorce":
            return f"divorced {others}" if own else f"{joined} divorced"
        if reason == "separation":
            return f"separated from {others}" if own else f"{joined} separated"
        if reason == "annulment":
            return f"marriage to {others} annulled" if own else f"Marriage of {joined} annulled"
        if own:
            return f"{noun.lower()} {'to' if kind == 'marriage' else 'with'} {others} ended"
        return f"{noun} of {joined} ended"
    verb = "born" if etype == "birth" else "died"
    if focus is not None and people[0] == focus:
        return verb
    return f"{shown[0]} {verb}"


_ROLE_KEYS = (("siblings", "sibling"), ("children", "child"), ("spouses", "spouse"), ("parents", "parent"))


def _person_rows(events: list[dict], info: dict, pid: str) -> list[tuple[dict, str]]:
    """Events that belong on one person's timeline, each with the relative's role."""
    roles: dict[str, str] = {}
    for key, role in _ROLE_KEYS:
        for other in info[key]:
            roles[other] = role
    first = last = None  # whole-year bounds of this person's own lifetime; None when that side is unknown
    for event in events:
        if event["people"] == [pid]:
            if event["type"] == "birth":
                first = event["year"]
            elif event["type"] == "death":
                last = event["year"]
    rows: list[tuple[dict, str]] = []
    for event in events:
        if pid in event["people"]:
            rows.append((event, "self"))
            continue
        if (first is not None and event["year"] < first) or (last is not None and event["year"] > last):
            continue
        role = next((roles[p] for p in event["people"] if p in roles), None)
        if role is None:
            continue
        etype = event["type"]
        if role == "parent":
            include = etype == "death"  # their wedding predates and is not about this person
        elif role == "spouse":
            include = etype == "death"
        elif role == "child":
            include = True
        else:
            include = etype in ("birth", "death")
        if include:
            rows.append((event, role))
    return rows


def build_timeline(tree: Tree, relations: Relations, living: set[str] | None = None) -> dict:
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

    names = {pid: tree.people[pid].display_name for pid in tree.people}
    for event in events:
        event["text"] = event_text(event, names, None)
    for pid in sorted(tree.people):
        birth = tree.people[pid].birth
        born = parse_date(birth.date) if birth else None
        rows = []
        for event, role in _person_rows(events, people[pid], pid):
            age, approx = None, False
            if role == "self" and event["type"] != "birth" and born is not None:
                at = ParsedDate(event["year"], event["month"], event["day"], event["approx"])
                age = age_between(born, at)
                approx = age is not None and (born.approx or at.approx)
            rows.append(
                {"id": event["id"], "role": role, "text": event_text(event, names, pid), "age": age, "age_approx": approx}
            )
        people[pid]["events"] = rows

    def position(date_text: str | None) -> float | None:
        parsed = parse_date(date_text)
        return year_position(parsed.year, parsed.month, parsed.day) if parsed else None

    starts: dict[str, float] = {}
    ends: dict[str, float] = {}
    for pid in sorted(tree.people):
        person = tree.people[pid]
        start = position(person.birth.date) if person.birth else None
        end = position(person.death.date) if person.death else None
        open_end = None
        if start is not None and end is None:
            open_end = "living" if pid in (living or set()) else "unknown"
        people[pid]["span"] = {"start": start, "end": end, "open": open_end}
        if start is not None:
            starts[pid] = start
        elif end is not None:
            ends[pid] = end

    def order(pid: str, at: float):
        return (at, tree.people[pid].display_name.lower(), pid)

    rows = [p for p in sorted(starts, key=lambda x: order(x, starts[x]))]
    rows += sorted(ends, key=lambda x: order(x, ends[x]))

    years = [e["year"] for e in events]
    return {
        "version": 1,
        "range": {"min": min(years) if years else None, "max": max(years) if years else None},
        "events": events,
        "people": people,
        "rows": rows,
        "undated": sorted(pid for pid in tree.people if pid not in dated),
    }
