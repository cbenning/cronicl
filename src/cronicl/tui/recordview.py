"""One record as the person screen shows it: a normalised list of rows, one leaf per row, each knowing its path in the
file, its line, any comment and any issue that points at it."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from ..core.inplace import _split_bom
from ..core.issues import Issue
from ..core.recordedit import EditRefused, _find_record, _root


@dataclass
class Row:
    label: str
    value: str = ""
    path: tuple = ()
    depth: int = 0
    line: int | None = None
    kind: str = "text"  # text | group | item | comment
    comment: str | None = None  # the `# ...` after the value on the same line
    comment_only: bool = False  # a whole-line comment inside the record
    extra: str = ""  # a person's name beside an id, for example
    raw: str = ""  # the value exactly as written (the display collapses whitespace)
    problems: list[Issue] = field(default_factory=list)


@dataclass
class RecordView:
    key: str
    rows: list[Row]
    first_line: int | None = None
    last_line: int | None = None


_LONG_FIELDS = ("bio", "note")


def _scalar_text(node) -> str:
    return " ".join(node.value.split()) if node.style not in ("|", ">") else node.value.strip("\n")


def _trailing_comment(lines: list[str], node) -> str | None:
    """A `# comment` after the end of `node` on its own last line."""
    row = node.end_mark.line
    if getattr(node, "style", None) in ("|", ">") or row >= len(lines):
        return None
    rest = lines[row][node.end_mark.column:]
    match = re.match(r"^[\s,\]}]*#\s?(.*)$", rest)
    return match.group(1).strip() if match else None


def build(text: str, key: str, issues: list[Issue], name_of) -> RecordView:
    """The rows of record `key` in `text`; `issues` are the issues of the whole file; `name_of(id)` names a person."""
    bom, body = _split_bom(text)
    try:
        root = _root(body)
        key_node, value_node = _find_record(root, key)
    except EditRefused:
        return RecordView(key, [])
    lines = body.split("\n")
    rows: list[Row] = []

    def visit(node, path, depth, parent_key=""):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                here = (*path, k.value)
                line = k.start_mark.line + 1
                if isinstance(v, yaml.MappingNode):
                    note = _trailing_comment(lines, v) if v.flow_style else _trailing_comment(lines, k)
                    rows.append(Row(k.value, "", here, depth, line, "group", note))
                    visit(v, here, depth + 1, k.value)
                elif isinstance(v, yaml.SequenceNode):
                    note = _trailing_comment(lines, v) if v.flow_style else _trailing_comment(lines, k)
                    rows.append(Row(k.value, "", here, depth, line, "group", note))
                    visit(v, here, depth + 1, k.value)
                else:
                    value = _scalar_text(v)
                    row = Row(k.value, value, here, depth, line, "text", _trailing_comment(lines, v))
                    row.raw = v.value.rstrip("\n") if getattr(v, "style", None) in ("|", ">") else v.value
                    rows.append(row)
        elif isinstance(node, yaml.SequenceNode):
            for index, item in enumerate(node.value):
                here = (*path, index)
                line = item.start_mark.line + 1
                if isinstance(item, yaml.MappingNode):
                    rows.append(Row("-", f"event {index + 1}" if parent_key == "events" else f"item {index + 1}", here, depth, line, "item"))
                    visit(item, here, depth + 1)
                else:
                    value = _scalar_text(item)
                    extra = name_of(value) if parent_key in ("parents", "adoptive-parents") else ""
                    rows.append(Row("-", value, here, depth, line, "text", _trailing_comment(lines, item), extra=extra, raw=item.value))

    if isinstance(value_node, yaml.MappingNode):
        visit(value_node, (key,), 0)
    first = key_node.start_mark.line + 1
    last = max([value_node.end_mark.line, key_node.end_mark.line]) + (0 if value_node.end_mark.column == 0 else 1)
    # whole-line comments inside the record (not the lines before its key, which belong to the previous record)
    for number in range(first + 1, last + 1):
        text_line = lines[number - 1].strip() if number - 1 < len(lines) else ""
        if text_line.startswith("#"):
            rows.append(Row("#", text_line.lstrip("# ").strip(), (), 0, number, "comment", comment_only=True))
    rows.sort(key=lambda r: (r.line or 0))
    # issues: attach each to the rows on its line (the rows whose label the message names when several share a line)
    for issue in issues:
        if issue.line is None or not (first <= issue.line <= last):
            continue
        hit = [r for r in rows if r.line == issue.line and not r.comment_only]
        named = [r for r in hit if re.search(rf"\b{re.escape(r.label)}\b", issue.message)]
        for r in named or hit:
            r.problems.append(issue)
    return RecordView(key, rows, first, last)
