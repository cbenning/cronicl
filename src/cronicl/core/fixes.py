"""Proposed fixes for warnings, as new text for the file that holds the problem. Nothing here writes anything.

Fixes that could mark someone deceased always ask: `death: no` most likely means alive, and the wrong guess would
remove a living person's privacy, so the safe answer (they are alive: take the death out) is the default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import SEX_WORDS
from .issues import Issue
from .model import Tree
from .recordedit import EditRefused, paths_at_line, record_data, remove, rename_key, set_value


@dataclass
class FixOption:
    label: str
    files: dict[str, str]  # the new text of each file the fix changes
    default: bool = False


def _steps(label: str) -> tuple:
    """`name.given` or `events[2].place` as path steps after the record key: ('name', 'given'), ('events', 1, 'place')."""
    out: list = []
    for part in label.split("."):
        match = re.fullmatch(r"(\w+)\[(\d+)\]", part)
        if match:
            out += [match.group(1), int(match.group(2)) - 1]
        else:
            out.append(part)
    return tuple(out)


def _pick(text: str, line: int | None, *, last=None, length=None, steps=None) -> tuple | None:
    for path in paths_at_line(text, line or 0):
        if steps is not None and path[1:] == steps:
            return path
        if last is not None and path[-1] == last and (length is None or len(path) == length):
            return path
    return None


def _one(issue: Issue, text: str, new: str, label: str, default: bool = False) -> FixOption:
    return FixOption(label, {issue.path: new}, default)


def fix_options(tree: Tree, files: dict[str, str], issue: Issue) -> list[FixOption]:
    """The fixes offered for `issue` (an empty list when it needs a human)."""
    text = files.get(issue.path or "")
    if text is None or issue.line is None:
        return []
    try:
        return _options(text, issue)
    except (EditRefused, KeyError, IndexError):
        return []


def _options(text: str, issue: Issue) -> list[FixOption]:
    code, message = issue.code, issue.message
    if code == "W-BLANK":
        match = re.search(r": (\S+) is blank", message)
        path = _pick(text, issue.line, steps=_steps(match.group(1))) if match else None
        return [_one(issue, text, remove(text, path), "remove the empty line")] if path else []
    if code == "W-UNKNOWN-KEY":
        match = re.search(r"unknown key '([^']+)' \(did you mean '([^']+)'\?\)", message)
        if not match:
            return []
        path = _pick(text, issue.line, steps=_steps(match.group(1)))
        return [_one(issue, text, rename_key(text, path, match.group(2)), f"rename it to {match.group(2)}")] if path else []
    if code == "W-DUPLICATE-PARENT":
        path = _pick(text, issue.line, last="parents", length=2)
        if not path:
            return []
        parents = record_data(text, path[0]).get("parents") or []
        new = text
        seen: set = set()
        drop = [i for i, p in enumerate(parents) if p in seen or seen.add(p)]
        for index in reversed(drop):
            new = remove(new, (*path, index))
        return [_one(issue, text, new, "remove the repeated parent")]
    if code == "W-BAD-SEX":
        path = _pick(text, issue.line, last="sex", length=2)
        return [_one(issue, text, set_value(text, path, word), word) for word in SEX_WORDS] if path else []
    if code == "W-COUPLE-EVENT-TYPE":
        match = re.search(r"did you mean '([^']+)'", message)
        path = next((p for p in paths_at_line(text, issue.line) if len(p) == 3 and p[1] == "events"), None)
        if not (match and path):
            return []
        return [_one(issue, text, set_value(text, (*path, "type"), match.group(1)), f"use {match.group(1)}")]
    if code in ("W-DATE-UNPARSED", "W-DEATH-EMPTY") and (code == "W-DEATH-EMPTY" or "death date" in message):
        path = next((p for p in paths_at_line(text, issue.line) if len(p) >= 2 and p[1] == "death"), None)
        if not path:
            return []
        record = path[0]
        data = record_data(text, record)
        if isinstance(data.get("death"), str):  # written fresh, so a quoted 'no' does not leave 'unknown' in quotes
            died = set_value(remove(text, (record, "death")), (record, "death"), "unknown")
        else:
            died = set_value(text, (record, "death", "date"), "unknown")
        return [
            _one(issue, text, remove(text, (record, "death")), "they are alive: remove the death line", default=True),
            _one(issue, text, died, "they died, date not known: write unknown"),
        ]
    if code == "W-LIVING-AND-DEATH":
        path = _pick(text, issue.line, last="living", length=2)
        if not path:
            return []
        record = path[0]
        return [
            _one(issue, text, remove(text, (record, "death")), "they are alive: remove the death", default=True),
            _one(issue, text, remove(text, (record, "living")), "they died: remove `living: true`"),
        ]
    return []
