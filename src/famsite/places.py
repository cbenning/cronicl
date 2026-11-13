from __future__ import annotations

from .model import Tree
from .relations import Relations
from .slug import slugify, unique_id


def place_index(tree: Tree, relations: Relations) -> list[dict]:
    """Every place named in the tree and what happened there: born, died, married or partnered.

    Places that differ only by case or surrounding space are one place; the spelling shown is the one on the lowest
    person id. Nothing is inferred: a place appears only where a file names it.
    """
    records: list[tuple[str, str, str, str | None, str]] = []  # (key, spelling, person id, what, date)
    for pid in sorted(tree.people):
        person = tree.people[pid]
        for what, event in (("born", person.birth), ("died", person.death)):
            if event and event.place and event.place.strip():
                records.append((event.place.strip().casefold(), event.place.strip(), pid, what, event.date))
    for cid in sorted(relations.couples):
        couple = relations.couples[cid]
        for entry in couple.partnerships:
            if entry.place and entry.place.strip():
                what = "married" if entry.type == "marriage" else "partnered"
                for pid in couple.partners:
                    records.append((entry.place.strip().casefold(), entry.place.strip(), pid, what, entry.start))
    groups: dict[str, dict] = {}
    for key, spelling, pid, what, when in records:
        group = groups.setdefault(key, {"spelling": (pid, spelling), "entries": []})
        group["spelling"] = min(group["spelling"], (pid, spelling))
        group["entries"].append({"id": pid, "what": what, "date": when})
    ordered = sorted(groups.items(), key=lambda item: (slugify(item[1]["spelling"][1]), item[0]))
    taken: set[str] = set()
    out: list[dict] = []
    for _, group in ordered:
        place = group["spelling"][1]
        slug = unique_id(slugify(place) or "place", taken)
        taken.add(slug)
        entries = sorted(group["entries"], key=lambda e: (e["date"] or "9999", e["id"], e["what"]))
        out.append({"place": place, "slug": slug, "entries": entries})
    return out
