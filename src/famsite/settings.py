"""The one safe reader for `site.yml` settings.

Values arrive as text (site.yml is loaded the way person files are) or as real Python values (trees are also built
in code), and an author can type anything. Nothing here raises, and a broken privacy setting fails closed: it
behaves as `placeholder`, never as `full`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MODES = ("full", "placeholder", "hidden")
DEFAULT_CUTOFF_YEARS = 100
_TRUE = ("true", "yes", "on", "1")
_FALSE = ("false", "no", "off", "0")
_INT = re.compile(r"^\s*\+?\d+\s*$")


def is_extension(key: str) -> bool:
    """`x-` / `x_` keys (any case) are the owner's own: never reported as unknown."""
    return str(key)[:2].casefold() in ("x-", "x_")


def parse_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    word = value.strip().casefold()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    return None


def parse_int(value, minimum: int = 1) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and _INT.match(value):
        number = int(value.strip().lstrip("+"))
    else:
        return None
    return number if number >= minimum else None


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
