from __future__ import annotations

from ..core.model import Tree
from ..core.relations import Relations
from ..core.slug import slugify, unique_id


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


def group_places(places: list[dict], aliases: dict | None = None) -> list[dict]:
    """Group places by the last comma-separated part of their name ("Hamburg, Germany" goes under Germany).

    Nothing is inferred: the group is whatever the name ends with. `aliases` (site.yml `place_groups`, matched
    ignoring case) folds a region into its country. A name with no comma joins a group only when it is that
    group's own name ("Germany"); every other one-part name goes under "Other places", which sorts last.
    """
    folded_aliases = {str(k).strip().casefold(): str(v).strip() for k, v in (aliases or {}).items() if str(v).strip()}

    def named(part: str) -> str:
        return folded_aliases.get(part.casefold(), part)

    def parts_of(place: str) -> list[str]:
        return [piece.strip() for piece in place.split(",") if piece.strip()]

    groups: dict[str, dict] = {}
    for entry in places:
        pieces = parts_of(entry["place"])
        if len(pieces) >= 2:
            name = named(pieces[-1])
            groups.setdefault(name.casefold(), {"name": name, "places": []})["places"].append(entry)
    other: list[dict] = []
    for entry in places:
        pieces = parts_of(entry["place"])
        if len(pieces) >= 2:
            continue
        key = named(pieces[0]).casefold() if pieces else ""
        if key in groups:
            groups[key]["places"].append(entry)
        else:
            other.append(entry)
    ordered = sorted(groups.values(), key=lambda g: (slugify(g["name"]), g["name"].casefold()))
    for group in ordered:  # keep the places in the order they were given (alphabetical)
        group["places"].sort(key=lambda e: places.index(e))
    taken = {"other"}
    out: list[dict] = []
    for group in ordered:
        slug = unique_id(slugify(group["name"]) or "group", taken)
        taken.add(slug)
        out.append({"name": group["name"], "slug": slug, "places": group["places"]})
    if other:
        out.append({"name": "Other places", "slug": "other", "places": other})
    return out
