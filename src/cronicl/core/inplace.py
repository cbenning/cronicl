"""Edit a family file without disturbing it: change only the characters that must change.

Positions come from YAML node marks, so comments, blank lines, order, quoting and line endings everywhere else stay
byte for byte as the owner wrote them. When a change cannot be made that way, `InplaceError` says what to edit by hand.
"""
from __future__ import annotations

import re

import yaml

from .yamltext import locate


class InplaceError(Exception):
    pass


def _split_bom(text: str) -> tuple[str, str]:
    return ("﻿", text[1:]) if text.startswith("﻿") else ("", text)


def _root(text: str):
    node = locate(text)
    if node is None or not isinstance(node, yaml.MappingNode):
        raise InplaceError("the file cannot be read as a mapping of records, so it cannot be edited automatically")
    return node


def _id_span(node) -> tuple[int, int]:
    """The span of a scalar's text, inside its quotes when it has them."""
    start, end = node.start_mark.index, node.end_mark.index
    return (start + 1, end - 1) if node.style in ('"', "'") else (start, end)


def rename(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace the person id `old` by `new` where it is an id: record keys, halves of couple keys, `parents` items."""
    bom, body = _split_bom(text)
    root = _root(body)
    spans: list[tuple[int, int]] = []
    token = re.compile(rf"(?<![a-z0-9-]){re.escape(old)}(?![a-z0-9-])")
    for key_node, value_node in root.value:
        key = key_node.value
        start, end = _id_span(key_node)
        if key == old:
            spans.append((start, end))
        elif "+" in key:
            for match in token.finditer(body[start:end]):
                spans.append((start + match.start(), start + match.end()))
        if isinstance(value_node, yaml.MappingNode):
            for inner_key, inner_value in value_node.value:
                if inner_key.value == "parents" and isinstance(inner_value, yaml.SequenceNode):
                    for item in inner_value.value:
                        if isinstance(item, yaml.ScalarNode) and item.value == old:
                            spans.append(_id_span(item))
    out = body
    for start, end in sorted(spans, reverse=True):
        out = out[:start] + new + out[end:]
    return bom + out, len(spans)


def _record(body: str, pid: str):
    root = _root(body)
    for key_node, value_node in root.value:
        if key_node.value == pid:
            return key_node, value_node
    raise InplaceError(f"no person record {pid!r} in this file")


def _last_line_end(body: str, end_index: int) -> int:
    """The index just past the line holding the last real character before `end_index`."""
    i = end_index
    while True:
        while i > 0 and body[i - 1] in " \t\r\n":
            i -= 1
        start = body.rfind("\n", 0, i) + 1
        if body[start:i].lstrip().startswith("#") and start > 0:  # a comment line that belongs to what follows
            i = start
            continue
        break
    nl = body.find("\n", i)
    return len(body) if nl == -1 else nl + 1


def _newline(body: str) -> str:
    return "\r\n" if "\r\n" in body else "\n"


def _insert_line(body: str, at: int, indent: int, line: str) -> str:
    newline = _newline(body)
    prefix = ""
    if at > 0 and body[at - 1] != "\n":
        prefix = newline  # the record's last line had no final newline
    return body[:at] + prefix + " " * indent + line + newline + body[at:]


def _children(value_node):
    if isinstance(value_node, yaml.MappingNode) and not value_node.flow_style and value_node.value:
        return {k.value: v for k, v in value_node.value}, value_node.value[0][0].start_mark.column
    return None, None


def _blank(value_node) -> bool:
    return isinstance(value_node, yaml.ScalarNode) and value_node.value == ""


def set_death_unknown(text: str, pid: str) -> str:
    """Add `death: unknown` to the person's record (after `birth` when there is one); unchanged when they have a death."""
    bom, body = _split_bom(text)
    key_node, value_node = _record(body, pid)
    if _blank(value_node):
        at = _last_line_end(body, key_node.end_mark.index)
        return bom + _insert_line(body, at, 2, "death: unknown")
    children, indent = _children(value_node)
    if children is None:
        raise InplaceError(f"{pid}: the record is written as {{...}} on one line; add `death: unknown` by hand")
    existing = children.get("death")
    if existing is not None:
        if isinstance(existing, yaml.ScalarNode) and not existing.value:  # blank: `death:` or `death:   # note`
            at = existing.start_mark.index
            return bom + body[:at] + (" " if body[at - 1:at] == ":" else "") + "unknown" + body[at:]
        return text
    anchor = children.get("birth") or children.get("sex") or children.get("name")
    if anchor is not None:
        at = _last_line_end(body, anchor.end_mark.index)
    else:
        first_key = value_node.value[0][0]
        at = body.rfind("\n", 0, first_key.start_mark.index) + 1
    return bom + _insert_line(body, at, indent, "death: unknown")


def set_living(text: str, pid: str) -> str:
    """Make the person's `living:` line `true`, adding it at the end of the record when it is missing."""
    bom, body = _split_bom(text)
    key_node, value_node = _record(body, pid)
    if _blank(value_node):
        at = _last_line_end(body, key_node.end_mark.index)
        return bom + _insert_line(body, at, 2, "living: true")
    children, indent = _children(value_node)
    if children is None:
        raise InplaceError(f"{pid}: the record is written as {{...}} on one line; add `living: true` by hand")
    existing = children.get("living")
    if existing is not None:
        if not isinstance(existing, yaml.ScalarNode):
            raise InplaceError(f"{pid}: `living` is not a single value; edit it by hand")
        if not existing.value:  # blank: `living:` or `living:   # note`
            at = existing.start_mark.index
            return bom + body[:at] + (" " if body[at - 1:at] == ":" else "") + "true" + body[at:]
        start, end = _id_span(existing)
        return text if existing.value == "true" else bom + body[:start] + "true" + body[end:]
    at = _last_line_end(body, value_node.end_mark.index)
    return bom + _insert_line(body, at, indent, "living: true")
