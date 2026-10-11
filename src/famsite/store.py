from __future__ import annotations

import re
from pathlib import Path

import yaml

from .issues import Issue
from .model import Event, Marriage, Person, Tree
from .slug import FALLBACK_SLUG, slugify

_FRONTMATTER = re.compile(r"\A---[ \t]*\n(?:(.*?)\n)?---[ \t]*(?:\n|\Z)(.*)\Z", re.S)
_DATE_LIKE = re.compile(r"^~?\d{4}(-\d{2}(-\d{2})?)?$")
PERSON_KEYS = (
    "id", "name", "sex", "birth", "death", "living",
    "parents", "spouse", "children", "marriages",
    "gedcom_id", "gedcom_extra",
)


# ---------------------------------------------------------------- parsing


def split_frontmatter(text: str) -> tuple[dict, str]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip("\n")
    raw = match.group(1) or ""
    # BaseLoader keeps every scalar a string: No/Null/1066 stay what the author wrote.
    data = yaml.load(raw, Loader=yaml.BaseLoader) if raw.strip() else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, match.group(2).strip("\n")


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
        return Event(date=_opt(value.get("date")), place=_opt(value.get("place")))
    text = _opt(value)
    return Event(date=text) if text else None


def _parse_name(value) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        return _opt(value.get("given")), _opt(value.get("surname"))
    text = _opt(value)
    if not text:
        return None, None
    parts = text.split()
    if len(parts) == 1:
        return parts[0], None
    return " ".join(parts[:-1]), parts[-1]


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


def _parse_marriages(value) -> list[Marriage]:
    if isinstance(value, dict):
        value = [value]
    out: list[Marriage] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        with_id = _opt(item.get("with"))
        if with_id:
            out.append(Marriage(with_id, _opt(item.get("date")), _opt(item.get("place"))))
    return out


def _make_person(data: dict, body: str, path: Path) -> Person:
    given, surname = _parse_name(data.get("name"))
    explicit = _opt(data.get("id"))
    return Person(
        id=explicit or slugify(path.stem) or FALLBACK_SLUG,
        given=given,
        surname=surname,
        sex=(_opt(data.get("sex")) or "U").upper(),
        birth=_parse_event(data.get("birth")),
        death=_parse_event(data.get("death")),
        living=_parse_bool(data.get("living")),
        parents=_as_list(data.get("parents")),
        spouse=_as_list(data.get("spouse")),
        children=_as_list(data.get("children")),
        marriages=_parse_marriages(data.get("marriages")),
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
            data, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            issues.append(Issue("E-BAD-FRONTMATTER", f"cannot parse frontmatter: {exc}", _rel(path, data_dir)))
            continue
        people.append(_make_person(data, body, path))
    return people, issues


def load_site(data_dir: Path) -> tuple[dict, list[Issue]]:
    path = Path(data_dir) / "site.yml"
    if not path.exists():
        return {}, [Issue("W-NO-SITE-YML", "site.yml not found; using defaults")]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return {}, [Issue("E-BAD-SITE-YML", f"cannot parse site.yml: {exc}", "site.yml")]
    if not isinstance(data, dict):
        return {}, [Issue("E-BAD-SITE-YML", "site.yml must be a mapping", "site.yml")]
    issues: list[Issue] = []
    if data.get("schema_version") not in (None, 1):
        issues.append(Issue("E-SCHEMA-VERSION", f"unsupported schema_version {data.get('schema_version')!r}", "site.yml"))
    return data, issues


def load_tree(data_dir: Path) -> tuple[Tree, list[Issue]]:
    data_dir = Path(data_dir)
    site, issues = load_site(data_dir)
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
    return lines


def _list_lines(key: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{key}:"] + [f"  - {_scalar(value)}" for value in values]


def _marriage_lines(marriages: list[Marriage]) -> list[str]:
    if not marriages:
        return []
    lines = ["marriages:"]
    for marriage in marriages:
        lines.append(f"  - with: {_scalar(marriage.with_id)}")
        if marriage.date:
            lines.append(f"    date: {_scalar(marriage.date)}")
        if marriage.place:
            lines.append(f"    place: {_scalar(marriage.place)}")
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
    if name:
        lines += ["name:"] + name
    if person.sex and person.sex != "U":
        lines.append(f"sex: {person.sex}")
    lines += _event_lines("birth", person.birth)
    lines += _event_lines("death", person.death)
    if person.living is not None:
        lines.append(f"living: {'true' if person.living else 'false'}")
    lines += _list_lines("parents", person.parents)
    lines += _list_lines("spouse", person.spouse)
    lines += _list_lines("children", person.children)
    lines += _marriage_lines(person.marriages)
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
