"""Checks for everything in `site.yml`: unknown keys, privacy, links, home, place groups, the gallery block."""
from __future__ import annotations

from ..core.issues import Issue
from ..core.textvalues import is_extension, parse_bool, parse_int
from ..core.validate import _hint, _unknown  # noqa: F401
from .galleries import gallery_issues
from .links import valid_contact, valid_edit_url
from .mapdata import map_issues
from .settings import privacy_settings

SITE_KNOWN = {"title", "intro", "home", "edit_url", "contact", "schema_version", "privacy", "place_groups", "gallery", "noindex", "places", "map"}
PRIVACY_KNOWN = {"living", "cutoff_years", "id_salt"}
SITE_TEXT_KEYS = ("title", "intro", "home", "edit_url", "contact")


def _is_collection(value) -> bool:
    return isinstance(value, (list, dict))


def site_issues(site: dict, people: dict) -> list[Issue]:
    out: list[Issue] = []
    if not isinstance(site, dict) or site.get("_unreadable"):
        return out
    path = "site.yml"
    _unknown([k for k in site if isinstance(k, str)], SITE_KNOWN, "", "", path, out)
    for key in SITE_TEXT_KEYS:
        if key in site and _is_collection(site[key]):
            out.append(Issue("W-SITE-VALUE", f"{key} must be text; it is ignored", path))
    if "noindex" in site and (_is_collection(site["noindex"]) or parse_bool(site["noindex"]) is None):
        out.append(Issue("W-SITE-VALUE", "noindex must be true or false; it is treated as false", path))
    if "place_groups" in site:
        groups = site["place_groups"]
        if not isinstance(groups, dict):
            out.append(Issue("W-SITE-VALUE", "place_groups must be a mapping of region: country; it is ignored", path))
        else:
            for key, value in groups.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    out.append(Issue("W-PLACE-GROUPS", f"place_groups entry {str(key)!r} must be text: text; it is ignored", path))
    if "privacy" in site:
        block = site["privacy"]
        if not isinstance(block, dict):
            out.append(Issue("E-PRIVACY-MODE", "privacy must be a mapping such as `living: placeholder`; living people are treated as placeholders", path))
        else:
            _unknown(list(block), PRIVACY_KNOWN, "", "privacy.", path, out)
            if "living" in block:
                setting = privacy_settings({"privacy": {"living": block["living"]}})
                if setting.broken:
                    out.append(Issue("E-PRIVACY-MODE", f"privacy.living {block['living']!r} is not full, placeholder or hidden; living people are treated as placeholders", path))
            if _is_collection(block.get("id_salt")):
                out.append(Issue("E-PRIVACY-SALT", "privacy.id_salt must be text; an empty salt makes anonymised ids guessable", path))
            if "cutoff_years" in block and parse_int(block["cutoff_years"]) is None:
                out.append(Issue("W-PRIVACY-CUTOFF", f"privacy.cutoff_years {block['cutoff_years']!r} is not a whole number of at least 1; 100 is used", path))
    settings = privacy_settings(site)
    if settings.living != "full" and not settings.salt and "privacy" in site and isinstance(site["privacy"], dict) and not _is_collection(site["privacy"].get("id_salt")):
        out.append(Issue("W-PRIVACY-NO-SALT", "privacy.id_salt is empty: anonymised ids of living people can be guessed from their real ids", path))
    return out


def site_check(site: dict, people: dict) -> list[Issue]:
    """Every issue about site.yml (links, home, gallery, settings)."""
    out: list[Issue] = []
    for key, valid in (("edit_url", valid_edit_url), ("contact", valid_contact)):
        value = (site or {}).get(key)
        if value and not valid(value):
            out.append(
                Issue(
                    "W-BAD-LINK",
                    f"{key} {str(value)!r} is not an allowed link (edit_url needs https://... and {{id}} or {{line}}; contact is mailto:, http:// or https://)",
                    "site.yml",
                )
            )
    out.extend(gallery_issues(site or {}, people))
    out.extend(map_issues(site or {}, people))
    home = (site or {}).get("home")
    if home and str(home) not in people:
        out.append(Issue("W-HOME-UNKNOWN", f"home {str(home)!r} is not a person id; the default home person is used", "site.yml"))
    out.extend(site_issues(site or {}, people))
    return out
