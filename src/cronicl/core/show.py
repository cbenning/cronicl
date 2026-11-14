"""`cronicl show ID`: one person the way the site sees them, with where each record lives."""
from __future__ import annotations

from .dates import format_date, format_years
from .model import Tree
from .relations import Relations


def _name(tree: Tree, pid: str) -> str:
    person = tree.people[pid]
    return f"{person.display_name} ({pid})"


def describe(tree: Tree, relations: Relations, pid: str) -> str:
    person = tree.people[pid]
    years = format_years(person.birth.date if person.birth else None, person.death.date if person.death else None)
    out = [f"{_name(tree, pid)}   {years}".rstrip()]
    if person.source:
        out.append(f"  record: {person.source}:{person.line}")
    if person.nickname or person.also:
        out.append("  also known as: " + ", ".join([n for n in [person.nickname, *person.also] if n]))
    for label, event in (("born", person.birth), ("died", person.death)):
        if event is not None:
            bits = [format_date(event.date)] if event.date else []
            if event.place:
                bits.append(f"in {event.place}")
            if bits:
                out.append(f"  {label}: " + " ".join(bits))
    parents = relations.parents.get(pid, [])
    if parents:
        out.append("  parents: " + ", ".join(_name(tree, p) for p in parents))
    for cid in relations.couples_of.get(pid, []):
        couple = relations.couples[cid]
        partner = next((p for p in couple.partners if p != pid), None)
        who = _name(tree, partner) if partner else "?"
        facts = []
        for entry in couple.partnerships:
            word = {"marriage": "married", "civil-union": "civil union", "engagement": "engaged", "partnership": "partners"}.get(entry.type or "", "together")
            facts.append(word + (f" {entry.start}" if entry.start else "") + (f" in {entry.place}" if entry.place else ""))
            if entry.end:
                facts.append((entry.end_reason or "ended") + (f" {entry.end}" if entry.end != "unknown" else ""))
        record = ""
        for other, _, source, line in getattr(tree.people[couple.partners[0]], "couple_records", []):
            if other == couple.partners[1]:
                record = f"   [couple record: {source}:{line}]"
        out.append(f"  partner: {who}" + (f" — {'; '.join(facts)}" if facts else "") + record)
        kids = relations.kids.get(cid, [])
        if kids:
            out.append("    children: " + ", ".join(_name(tree, k) for k in kids))
    siblings = sorted({c for p in parents for cid in relations.couples_of.get(p, []) for c in relations.kids.get(cid, []) if c != pid})
    if siblings:
        out.append("  siblings: " + ", ".join(_name(tree, s) for s in siblings))
    for event in person.events:
        when = format_date(event.date) if event.date else format_date(f"FROM {event.start} TO {event.end}" if event.start and event.end else (f"FROM {event.start}" if event.start else (f"TO {event.end}" if event.end else "")))
        bits = [event.type.replace("-", " ") or "event"] + ([event.value] if event.value else []) + ([when] if when else []) + ([f"in {event.place}"] if event.place else [])
        out.append("  event: " + " ".join(bits))
    if person.gedcom_id or person.gallery_id:
        out.append("  refs: " + ", ".join(f"{k} {v}" for k, v in (("gedcom", person.gedcom_id), ("gallery", person.gallery_id)) if v))
    return "\n".join(out) + "\n"
