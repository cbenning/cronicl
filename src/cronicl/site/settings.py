"""The one safe reader for `site.yml` settings.

Values arrive as text (site.yml is loaded the way person files are) or as real Python values (trees are also built
in code), and an author can type anything. Nothing here raises, and a broken privacy setting fails closed: it
behaves as `placeholder`, never as `full`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.textvalues import is_extension, parse_bool, parse_int  # noqa: F401  (re-exported)

MODES = ("full", "placeholder", "hidden")
DEFAULT_CUTOFF_YEARS = 100


@dataclass(frozen=True)
class Privacy:
    living: str  # the effective mode: always one of MODES
    cutoff_years: int
    salt: str
    broken: bool  # a setting was unusable and the safe fallback is in force


def privacy_settings(site: dict) -> Privacy:
    site = site if isinstance(site, dict) else {}
    closed = bool(site.get("_unreadable"))  # site.yml could not be read: the owner's intent is unknown
    block = site.get("privacy", {}) if "privacy" in site else {}
    if not isinstance(block, dict):
        closed, block = True, {}
    living = "full"
    if "living" in block:
        raw = block["living"]
        mode = "" if raw is None else str(raw).strip().casefold()
        if mode in MODES:
            living = mode
        else:
            closed = True
    raw_salt = block.get("id_salt")
    broken = closed or isinstance(raw_salt, (list, dict))
    salt = "" if raw_salt is None or isinstance(raw_salt, (list, dict)) else str(raw_salt)
    if closed:
        living = "placeholder"
    return Privacy(
        living=living, cutoff_years=parse_int(block.get("cutoff_years")) or DEFAULT_CUTOFF_YEARS, salt=salt, broken=broken
    )


def site_text(site: dict, key: str, default: str = "") -> str:
    value = site.get(key) if isinstance(site, dict) else None
    if isinstance(value, (list, dict)) or value is None:
        return default
    text = str(value).strip()
    return text or default


def place_groups(site: dict) -> dict[str, str]:
    groups = site.get("place_groups") if isinstance(site, dict) else None
    if not isinstance(groups, dict):
        return {}
    return {k: v for k, v in groups.items() if isinstance(k, str) and isinstance(v, str)}
