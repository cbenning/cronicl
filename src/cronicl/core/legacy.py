"""The old data layout: one markdown file per person (people/*.md). Read only, and only for `cronicl migrate`."""
from __future__ import annotations

import re
from pathlib import Path

from .issues import Issue
from .model import Event, LifeEvent, Partnership, Person, Tree
from .slug import FALLBACK_SLUG, slugify
from .textvalues import cites_of
from .yamltext import load_text

_FRONTMATTER = re.compile(r"\A---[ \t]*\n(?:(.*?)\n)?---[ \t]*(?:\n|\Z)(.*)\Z", re.S)
_DATE_LIKE = re.compile(r"^~?\d{4}(-\d{2}(-\d{2})?)?$")
PERSON_KEYS = (
    "id", "name", "sex", "birth", "death", "living", "portrait", "gallery_id",
    "parents", "spouse", "children", "marriages", "partnerships", "events",
    "gedcom_id", "gedcom_extra",
)


# ---------------------------------------------------------------- parsing


def split_frontmatter(text: str) -> tuple[dict, str]:
    data, body, _ = split_frontmatter_checked(text)
    return data, body


def split_frontmatter_checked(text: str) -> tuple[dict, str, list[str]]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip("\n"), []
    raw = match.group(1) or ""
    result = load_text(raw) if raw.strip() else None
    if result is not None and result.error:
        raise ValueError(result.error)
    data = result.data if result is not None else {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, match.group(2).strip("\n"), [key for key, _ in (result.duplicates if result else [])]


def _opt(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _parse_event(value) -> Event | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return Event(
            date=_opt(value.get("date")),
            place=_opt(value.get("place")),
            extra={k: v for k, v in value.items() if k not in ("date", "place")},
        )
    text = _opt(value)
    return Event(date=text) if text else None


def _parse_name(value) -> tuple[str | None, str | None, dict]:
    if isinstance(value, dict):
        extra = {k: v for k, v in value.items() if k not in ("given", "surname")}
        return _opt(value.get("given")), _opt(value.get("surname")), extra
    text = _opt(value)
    if not text:
        return None, None, {}
    parts = text.split()
    if len(parts) == 1:
        return parts[0], None, {}
    return " ".join(parts[:-1]), parts[-1], {}


def _parse_bool(value) -> bool | None:
    text = _opt(value)
    if text is None:
        return None
    lowered = str(text).lower()
    if lowered in ("true", "yes", "on", "1"):
        return True
    if lowered in ("false", "no", "off", "0"):
        return False
    return None


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


_EVENT_KEYS = ("type", "date", "start", "end", "place", "value", "note", "cite")


def _parse_events(data: dict) -> list[LifeEvent]:
    out: list[LifeEvent] = []
    for item in _partnership_items(data.get("events")):  # one mapping is one entry, as for partnerships
        out.append(
            LifeEvent(
                type=_opt(item.get("type")) or "",
                date=_opt(item.get("date")),
                start=_opt(item.get("start")),
                end=_opt(item.get("end")),
                place=_opt(item.get("place")),
                value=_opt(item.get("value")),
                note=_opt(item.get("note")),
                cite=cites_of(item.get("cite")),
                extra={k: v for k, v in item.items() if k not in _EVENT_KEYS},
            )
        )
    return out


_PARTNERSHIP_KEYS = ("with", "type", "start", "end", "end_reason", "place", "note", "date")


def _partnership_items(value) -> list[dict]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and item]


def _parse_partnerships(data: dict) -> list[Partnership]:
    """`partnerships:` entries, then legacy `marriages:` entries (which are marriages unless they say otherwise)."""
    out: list[Partnership] = []
    for key, default_type in (("partnerships", None), ("marriages", "marriage")):
        for item in _partnership_items(data.get(key)):
            out.append(
                Partnership(
                    with_id=_opt(item.get("with")) or "",
                    type=_opt(item.get("type")) or default_type,
                    start=_opt(item.get("start")) or _opt(item.get("date")),
                    end=_opt(item.get("end")),
                    end_reason=_opt(item.get("end_reason")),
                    place=_opt(item.get("place")),
                    note=_opt(item.get("note")),
                    extra={k: v for k, v in item.items() if k not in _PARTNERSHIP_KEYS},
                )
            )
    return out


def _require_text(value, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a single value, not a list or mapping")


def _require_text_list(value, label: str) -> None:
    if value is None or isinstance(value, str):
        return
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a value or a list of values")


def _require_mapping_of_text(value, label: str, keys: tuple[str, ...]) -> None:
    if value is None or isinstance(value, str):
        return
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a value or a mapping")
    for key in keys:
        _require_text(value.get(key), f"{label}.{key}")


def _validate_shapes(data: dict) -> None:
    """Reject well-formed YAML whose values have the wrong shape (a list where text is expected, ...)."""
    for key in ("id", "sex", "living", "portrait", "gallery_id", "gedcom_id", "gedcom_extra"):
        _require_text(data.get(key), key)
    _require_mapping_of_text(data.get("name"), "name", ("given", "surname"))
    _require_mapping_of_text(data.get("birth"), "birth", ("date", "place"))
    _require_mapping_of_text(data.get("death"), "death", ("date", "place"))
    for key in ("parents", "spouse", "children"):
        _require_text_list(data.get(key), key)
    entries = data.get("events")
    if entries is not None and not isinstance(entries, (dict, list)):
        raise ValueError("events must be a list of mappings")
    for item in [entries] if isinstance(entries, dict) else entries or []:
        if not isinstance(item, dict):
            raise ValueError("events entries must be mappings")
        for field_name in _EVENT_KEYS[:-1]:
            _require_text(item.get(field_name), f"events.{field_name}")
        _require_text_list(item.get("cite"), "events.cite")
    for key in ("partnerships", "marriages"):
        entries = data.get(key)
        if entries is not None and not isinstance(entries, (str, dict, list)):
            raise ValueError(f"{key} must be a list of mappings")
        if isinstance(entries, dict):
            entries = [entries]
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    raise ValueError(f"{key} entries must be mappings")
                for field_name in _PARTNERSHIP_KEYS:
                    _require_text(item.get(field_name), f"{key}.{field_name}")


def _make_person(data: dict, body: str, path: Path) -> Person:
    given, surname, name_extra = _parse_name(data.get("name"))
    explicit = _opt(data.get("id"))
    return Person(
        id=explicit or slugify(path.stem) or FALLBACK_SLUG,
        given=given,
        surname=surname,
        name_extra=name_extra,
        sex=(_opt(data.get("sex")) or "U").upper(),
        birth=_parse_event(data.get("birth")),
        death=_parse_event(data.get("death")),
        living=_parse_bool(data.get("living")),
        living_text=str(data["living"]).strip() if data.get("living") is not None else None,
        portrait=_opt(data.get("portrait")),
        gallery_id=_opt(data.get("gallery_id")),
        parents=_as_list(data.get("parents")),
        spouse=_as_list(data.get("spouse")),
        children=_as_list(data.get("children")),
        partnerships=_parse_partnerships(data),
        events=_parse_events(data),
        gedcom_id=_opt(data.get("gedcom_id")),
        gedcom_extra=_opt(data.get("gedcom_extra")),
        body=body,
        extra={k: v for k, v in data.items() if k not in PERSON_KEYS},
        path=path,
        id_pinned=explicit is not None,
    )


def _rel(path: Path, data_dir: Path) -> str:
    try:
        return path.relative_to(data_dir).as_posix()
    except ValueError:
        return str(path)


def read_legacy(data_dir: Path) -> tuple[list[Person], list[Issue]]:
    data_dir = Path(data_dir)
    people: list[Person] = []
    issues: list[Issue] = []
    for path in sorted((data_dir / "people").glob("*.md")):
        try:
            data, body, duplicates = split_frontmatter_checked(path.read_text(encoding="utf-8"))
            _validate_shapes(data)
        except (ValueError, UnicodeDecodeError) as exc:
            issues.append(Issue("E-BAD-FRONTMATTER", f"cannot parse frontmatter: {exc}", _rel(path, data_dir)))
            continue
        for key in duplicates:
            issues.append(Issue("W-DUPLICATE-KEY", f"duplicate key {key!r}; the later value is used", _rel(path, data_dir)))
        people.append(_make_person(data, body, path))
    return people, issues




def load_legacy_tree(data_dir: Path) -> tuple[Tree, list[Issue]]:
    """The people of an old folder as a Tree (site.yml is loaded separately by the caller)."""
    data_dir = Path(data_dir)
    people, issues = read_legacy(data_dir)
    tree = Tree()
    for person in people:
        if person.id in tree.people:
            first = tree.people[person.id].path
            issues.append(Issue("E-DUPLICATE-ID", f"person id {person.id!r} is also used by {first.name}", _rel(person.path, data_dir)))
            continue
        tree.people[person.id] = person
    return tree, issues
