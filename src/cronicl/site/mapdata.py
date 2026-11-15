"""The optional map: coordinates for places (`places:`), the `map:` block of site.yml, and the markers on the map page.

Everything in `places:` and `map:` is published to visitors, like the other site.yml settings the site uses. With no
`map:` block there is no map page and the site makes no request to a tile server.
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

from ..core.issues import Issue
from ..core.textvalues import is_extension

DEFAULT_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors"
DEFAULT_LABEL = "Map"
MAP_KEYS = ("type", "tiles", "attribution", "label")
MAP_TYPES = ("osm",)
MAX_TEXT = 200
_PLACEHOLDERS = re.compile(r"\{[^{}]*\}")


def norm_place(text) -> str:
    """The key a place is looked up by: case-folded, whitespace collapsed."""
    return " ".join(str(text).split()).casefold()


def _coords(value) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, str) for v in value):
        return None
    try:
        lat, lon = float(value[0]), float(value[1])
    except ValueError:
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def place_coords(site: dict) -> dict[str, tuple[float, float]]:
    """Usable coordinates by normalised place name; entries that are not `[lat, lon]` in range are skipped."""
    table = (site or {}).get("places")
    if not isinstance(table, dict):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for name, value in table.items():
        found = _coords(value)
        if isinstance(name, str) and name.strip() and found is not None:
            out.setdefault(norm_place(name), found)
    return out


def _valid_tiles(value) -> bool:
    if not isinstance(value, str) or any(c.isspace() or c in "\"'<>\\`" for c in value):
        return False
    try:
        parts = urlsplit(value.replace("{", "x").replace("}", "x"))
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.netloc or "@" in parts.netloc:
        return False
    return sorted(_PLACEHOLDERS.findall(value)) == ["{x}", "{y}", "{z}"]


def _text(value, default: str) -> str:
    text = " ".join(str(value).split())[:MAX_TEXT] if isinstance(value, str) else ""
    return text or default


def map_settings(site: dict) -> dict | None:
    """The normalised `map:` block when it is valid, else None. Never raises."""
    block = (site or {}).get("map")
    if not isinstance(block, dict) or block.get("type") not in MAP_TYPES:
        return None
    tiles = block.get("tiles", DEFAULT_TILES)
    if not _valid_tiles(tiles):
        return None
    return {
        "type": block["type"], "tiles": tiles, "attribution": _text(block.get("attribution"), DEFAULT_ATTRIBUTION),
        "label": _text(block.get("label"), DEFAULT_LABEL)[:40],
    }


def _used_places(people: dict) -> set[str]:
    used: set[str] = set()
    for person in people.values():
        for event in (person.birth, person.death):
            if event and event.place:
                used.add(norm_place(event.place))
        used.update(norm_place(e.place) for e in person.events if e.place)
        used.update(norm_place(p.place) for p in person.partnerships if p.place)
    return used


def map_issues(site: dict, people: dict) -> list[Issue]:
    out: list[Issue] = []
    site = site or {}
    table = site.get("places")
    usable = place_coords(site)
    if "places" in site:
        if not isinstance(table, dict):
            out.append(Issue("W-SITE-VALUE", "places must be a mapping of place: [latitude, longitude]; it is ignored", "site.yml"))
        else:
            for name, value in table.items():
                if not isinstance(name, str) or not name.strip() or _coords(value) is None:
                    out.append(
                        Issue("W-PLACE-COORDS", f"places entry {str(name)!r} must be text: [latitude, longitude] (-90..90, -180..180); it is ignored", "site.yml")
                    )
            used = _used_places(people)
            for name in table:
                if isinstance(name, str) and norm_place(name) in usable and norm_place(name) not in used:
                    out.append(Issue("W-PLACE-UNKNOWN", f"places entry {name!r} matches no place in family.yml", "site.yml"))
    if "map" in site:
        block = site["map"]
        if not isinstance(block, dict) or block.get("type") not in MAP_TYPES:
            out.append(Issue("E-MAP-TYPE", f"map needs a mapping with a type, one of: {', '.join(MAP_TYPES)}", "site.yml"))
        else:
            if "tiles" in block and not _valid_tiles(block["tiles"]):
                out.append(Issue("E-MAP-TILES", "map tiles must be an http:// or https:// address containing {z}, {x} and {y} and no other braces", "site.yml"))
            for key in block:
                if key not in MAP_KEYS and not is_extension(key):
                    out.append(Issue("W-MAP-KEY", f"map key {str(key)!r} is not used; valid keys are {', '.join(MAP_KEYS)}", "site.yml"))
            if map_settings(site) is not None and not usable:
                out.append(Issue("W-MAP-NO-COORDS", "map is configured but places gives no usable coordinates, so the map is empty", "site.yml"))
    return out


def map_markers(places: list[dict], coords: dict[str, tuple[float, float]]) -> list[dict]:
    """One marker per place on the places page that has coordinates. `places` is `place_index(...)` with names added."""
    markers = []
    for place in places:
        found = coords.get(norm_place(place["place"]))
        if found is None:
            continue
        markers.append({
            "name": place["place"], "slug": place["slug"], "lat": found[0], "lon": found[1],
            "entries": [{"id": e["id"], "name": e["name"], "what": e["what"], "when": e.get("when") or ""} for e in place["entries"]],
        })
    return markers
