"""Reading values typed by a person: yes/no words, whole numbers, and the `x-` extension-key convention."""
from __future__ import annotations

import re

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


def cites_of(value) -> list[str]:
    """Citations as a list: one string is one citation, a list keeps its non-empty strings, anything else is none."""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []
