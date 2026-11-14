from __future__ import annotations

import re
from pathlib import Path

import yaml

from .family import has_family, read_family
from .issues import Issue
from .model import Event, LifeEvent, Partnership, Person, Tree
from .slug import FALLBACK_SLUG, slugify

_FRONTMATTER = re.compile(r"\A---[ \t]*\n(?:(.*?)\n)?---[ \t]*(?:\n|\Z)(.*)\Z", re.S)
_DATE_LIKE = re.compile(r"^~?\d{4}(-\d{2}(-\d{2})?)?$")
PERSON_KEYS = (
    "id", "name", "sex", "birth", "death", "living", "portrait", "gallery_id",
    "parents", "spouse", "children", "marriages", "partnerships", "events",
    "gedcom_id", "gedcom_extra",
)


# ---------------------------------------------------------------- parsing


class _TextLoader(yaml.BaseLoader):
    """Keeps every scalar a string (No, Null, 1066 stay what the author wrote) and remembers repeated keys."""

    def __init__(self, stream):
        super().__init__(stream)
        self.duplicates: list[str] = []
        self.merge_keys = False

    def construct_mapping(self, node, deep=False):
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                hash(key)
            except TypeError:
                continue  # a list or mapping used as a key: the base class reports it as a YAML error
            if key == "<<":
                self.merge_keys = True
            if key in seen:
                self.duplicates.append(str(key))
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml_text(raw: str, *, allow_merge: bool = True) -> tuple[object, list[str]]:
    """Parse YAML with every scalar as text; returns the data and the names of keys written twice in one mapping.

    This loader does not apply merge keys (`<<`). Where a silent miss could be harmful (site.yml carries the privacy
    setting) the caller passes allow_merge=False and a merge key is an error instead of an ignored line.
    """
    loader = _TextLoader(raw)
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    if loader.merge_keys and not allow_merge:
        raise yaml.YAMLError("merge keys (<<) are not supported in site.yml; write the values out")
    return data, loader.duplicates


def split_frontmatter(text: str) -> tuple[dict, str]:
    data, body, _ = split_frontmatter_checked(text)
    return data, body


def split_frontmatter_checked(text: str) -> tuple[dict, str, list[str]]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip("\n"), []
    raw = match.group(1) or ""
    data, duplicates = load_yaml_text(raw) if raw.strip() else ({}, [])
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, match.group(2).strip("\n"), duplicates


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


def cites_of(value) -> list[str]:
    """Citations as a list: one string is one citation, a list keeps its non-empty strings, anything else is none."""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


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


def read_records(data_dir: Path) -> tuple[list[Person], list[Issue]]:
    data_dir = Path(data_dir)
    people: list[Person] = []
    issues: list[Issue] = []
    for path in sorted((data_dir / "people").glob("*.md")):
        try:
            data, body, duplicates = split_frontmatter_checked(path.read_text(encoding="utf-8"))
            _validate_shapes(data)
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            issues.append(Issue("E-BAD-FRONTMATTER", f"cannot parse frontmatter: {exc}", _rel(path, data_dir)))
            continue
        for key in duplicates:
            issues.append(Issue("W-DUPLICATE-KEY", f"duplicate key {key!r}; the later value is used", _rel(path, data_dir)))
        people.append(_make_person(data, body, path))
    return people, issues


def load_site(data_dir: Path) -> tuple[dict, list[Issue]]:
    path = Path(data_dir) / "site.yml"
    if not path.exists():
        return {}, [Issue("W-NO-SITE-YML", "site.yml not found; using defaults")]
    unreadable = {"_unreadable": True}  # the owner's intent is unknown, so settings fail closed
    try:
        data, duplicates = load_yaml_text(path.read_text(encoding="utf-8"), allow_merge=False)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return unreadable, [Issue("E-BAD-SITE-YML", f"cannot parse site.yml: {exc}", "site.yml")]
    if data is None or data == "":
        data = {}
    if not isinstance(data, dict):
        return unreadable, [Issue("E-BAD-SITE-YML", "site.yml must be a mapping", "site.yml")]
    issues: list[Issue] = [
        Issue("W-DUPLICATE-KEY", f"duplicate key {key!r}; the later value is used", "site.yml") for key in duplicates
    ]
    version = data.get("schema_version")
    if version is not None and not (isinstance(version, str) and version.strip() in ("1", "2", "3")):
        issues.append(Issue("E-SCHEMA-VERSION", f"unsupported schema_version {version!r}", "site.yml"))
    return data, issues


def load_tree(data_dir: Path) -> tuple[Tree, list[Issue]]:
    data_dir = Path(data_dir)
    site, issues = load_site(data_dir)
    if has_family(data_dir):
        people, record_issues = read_family(data_dir)
    else:  # until the old layout is removed (see the family-file plan), an old folder still loads
        people, record_issues = read_records(data_dir)
    issues = issues + record_issues
    tree = Tree(site=site)
    for person in people:
        if person.id in tree.people:
            first = tree.people[person.id].path
            issues.append(
                Issue("E-DUPLICATE-ID", f"person id {person.id!r} is also used by {first.name}", _rel(person.path, data_dir))
            )
            continue
        tree.people[person.id] = person
    return tree, issues


# ---------------------------------------------------------------- writing


def _scalar(value: str) -> str:
    if _DATE_LIKE.match(value):
        return value
    dumped = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=10**9)
    return dumped.removesuffix("\n...\n").strip()


def _extra_lines(extra: dict, indent: int) -> list[str]:
    if not extra:
        return []
    dumped = yaml.safe_dump(extra, sort_keys=False, allow_unicode=True, width=10**9)
    return [" " * indent + line for line in dumped.rstrip("\n").split("\n")]


def _event_lines(key: str, event: Event | None) -> list[str]:
    if event is None:
        return []
    if event.is_empty():
        return [f"{key}: {{}}"]
    lines = [f"{key}:"]
    if event.date:
        lines.append(f"  date: {_scalar(event.date)}")
    if event.place:
        lines.append(f"  place: {_scalar(event.place)}")
    lines += _extra_lines(event.extra, 2)
    return lines


def _list_lines(key: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{key}:"] + [f"  - {_scalar(value)}" for value in values]


def _partnership_lines(partnerships: list[Partnership]) -> list[str]:
    if not partnerships:
        return []
    lines = ["partnerships:"]
    for entry in partnerships:
        fields = (
            ("with", entry.with_id), ("type", entry.type), ("start", entry.start), ("end", entry.end),
            ("end_reason", entry.end_reason), ("place", entry.place), ("note", entry.note),
        )
        block = [f"{key}: {_scalar(value)}" for key, value in fields if value]
        block += _extra_lines(entry.extra, 0)
        if not block:
            continue
        lines.append(f"  - {block[0]}")
        lines += [f"    {line}" for line in block[1:]]
    return lines


def _event_entry_lines(events: list[LifeEvent]) -> list[str]:
    if not events:
        return []
    lines = ["events:"]
    for entry in events:
        fields = (
            ("type", entry.type), ("date", entry.date), ("start", entry.start), ("end", entry.end),
            ("place", entry.place), ("value", entry.value), ("note", entry.note),
        )
        block = [f"{key}: {_scalar(value)}" for key, value in fields if value]
        if entry.cite:
            block += ["cite:"] + [f"  - {_scalar(text)}" for text in entry.cite]
        block += _extra_lines(entry.extra, 0)
        if not block:
            continue
        lines.append(f"  - {block[0]}")
        lines += [f"    {line}" for line in block[1:]]
    return lines


def _extra_block(text: str) -> list[str]:
    header = "gedcom_extra: |2-" if text[:1] in (" ", "\t") else "gedcom_extra: |-"
    return [header] + [("  " + line) if line else "" for line in text.split("\n")]


def _assemble(front: str, body: str) -> str:
    out = "---\n" + front + "---\n"
    if body.strip():
        out += "\n" + body.strip("\n") + "\n"
    return out


def dump_person(person: Person) -> str:
    lines = [f"id: {_scalar(person.id)}"]
    name = []
    if person.given:
        name.append(f"  given: {_scalar(person.given)}")
    if person.surname:
        name.append(f"  surname: {_scalar(person.surname)}")
    name += _extra_lines(person.name_extra, 2)
    if name:
        lines += ["name:"] + name
    if person.sex and person.sex != "U":
        lines.append(f"sex: {person.sex}")
    lines += _event_lines("birth", person.birth)
    lines += _event_lines("death", person.death)
    if person.living is not None:
        lines.append(f"living: {'true' if person.living else 'false'}")
    if person.portrait:
        lines.append(f"portrait: {_scalar(person.portrait)}")
    if person.gallery_id:
        lines.append(f"gallery_id: {_scalar(person.gallery_id)}")
    lines += _list_lines("parents", person.parents)
    lines += _list_lines("spouse", person.spouse)
    lines += _list_lines("children", person.children)
    lines += _partnership_lines(person.partnerships)
    lines += _event_entry_lines(person.events)
    if person.gedcom_id:
        lines.append(f"gedcom_id: {_scalar(person.gedcom_id)}")
    if person.gedcom_extra:
        lines += _extra_block(person.gedcom_extra)
    front = "\n".join(lines) + "\n"
    if person.extra:
        front += yaml.safe_dump(person.extra, sort_keys=False, allow_unicode=True)
    return _assemble(front, person.body)


def person_path(data_dir: Path, person_id: str) -> Path:
    return Path(data_dir) / "people" / f"{person_id}.md"


def write_person(data_dir: Path, person: Person) -> Path:
    path = person_path(data_dir, person.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_person(person), encoding="utf-8")
    return path
