"""The commands that edit family files in place: rename a person, mark people deceased or living."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .edit import EditError
from .family import family_files
from .inplace import InplaceError, _id_span, _root, _split_bom, rename, set_death_unknown, set_living
from .slug import is_valid_id
from .store import load_tree


@dataclass
class Change:
    path: Path
    text: str
    count: int = 0


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _rename_home(path: Path, old: str, new: str) -> Change | None:
    if not path.exists():
        return None
    text = _read(path)
    bom, body = _split_bom(text)
    try:
        root = _root(body)
    except InplaceError:
        return None
    for key_node, value_node in root.value:
        if key_node.value == "home" and isinstance(value_node, yaml.ScalarNode) and value_node.value == old:
            start, end = _id_span(value_node)
            return Change(path, bom + body[:start] + new + body[end:], 1)
    return None


def plan_rename(data_dir: Path, old: str, new: str) -> list[Change]:
    data_dir = Path(data_dir)
    tree, _ = load_tree(data_dir)
    if old not in tree.people:
        raise EditError(f"no person {old!r}; use cronicl search to find ids")
    if not is_valid_id(new):
        raise EditError(f"{new!r} is not a valid id (lower-case letters, digits and single hyphens)")
    if new == old:
        raise EditError("the new id is the same as the old one")
    if new in tree.people:
        raise EditError(f"{new} already exists")
    changes: list[Change] = []
    for path in family_files(data_dir):
        try:
            updated, count = rename(_read(path), old, new)
        except InplaceError as exc:
            raise EditError(f"{path.name}: {exc}") from None
        if count:
            changes.append(Change(path, updated, count))
    home = _rename_home(data_dir / "site.yml", old, new)
    if home:
        changes.append(home)
    extra = data_dir / "archive" / "gedcom-extra.yml"  # what the importer set aside is filed under the person's id
    if extra.is_file():
        try:
            updated, count = rename(_read(extra), old, new)
        except (InplaceError, UnicodeDecodeError):
            updated, count = "", 0
        if count:
            changes.append(Change(extra, updated, count))
    return changes


def plan_mark(data_dir: Path, ids: list[str], living: bool) -> list[tuple[str, Path, bool, str]]:
    """For each id: (id, file, changes?, new text of the file after this and the earlier ids' edits)."""
    data_dir = Path(data_dir)
    tree, _ = load_tree(data_dir)
    unknown = [pid for pid in ids if pid not in tree.people]
    if unknown:
        raise EditError("unknown person id(s): " + ", ".join(unknown) + "; use `cronicl search` to find ids")
    texts: dict[Path, str] = {}
    results: list[tuple[str, Path, bool, str]] = []
    seen: set[str] = set()
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        path = data_dir / tree.people[pid].source
        current = texts.get(path) or _read(path)
        try:
            updated = set_living(current, pid) if living else set_death_unknown(current, pid)
        except InplaceError as exc:
            message = str(exc)
            raise EditError(message if message.startswith(f"{pid}:") else f"{pid}: {message}") from None
        texts[path] = updated
        results.append((pid, path, updated != current, updated))
    return results
