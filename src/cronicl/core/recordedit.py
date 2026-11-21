"""Edit one record of a family file as text: text in, text out, every byte outside the change left as it was.

Positions come from YAML node marks (as in `inplace.py`). A path names a value from the record key down:
`("lovelace-ada", "birth", "date")`, `("lovelace-ada", "events", 0, "type")`, `("byron-george + milbanke-annabella", "note")`.
When a change cannot be made in place (a flow mapping that would grow past 100 characters, the first key of a `- ` list
item) the one record is rewritten in the canonical block style of `emit.py`: comments inside that record are lost, and
the diff the TUI shows says so. Nothing outside the record ever changes.
"""
from __future__ import annotations

import re

import yaml

from .emit import quote
from .inplace import _last_line_end, _newline, _split_bom
from .yamltext import Mapping, Sequence, load_text, locate

LONG = 100  # the longest line the editor writes into a flow mapping

PERSON_ORDER = ("name", "sex", "birth", "death", "parents", "adoptive-parents", "events", "portrait", "living", "refs", "bio")
COUPLE_ORDER = ("events", "note")
NAME_ORDER = ("given", "surname", "prefix", "suffix", "nickname", "also")
VITAL_ORDER = ("date", "place", "note", "cite")
EVENT_ORDER = ("type", "date", "place", "value", "note", "cite")
REFS_ORDER = ("gedcom", "gallery")
_NESTED_ORDER = {"name": NAME_ORDER, "birth": VITAL_ORDER, "death": VITAL_ORDER, "refs": REFS_ORDER}
_DICT_KEYS = ("name", "birth", "death", "refs")  # values that are mappings (birth and death may be a bare date)


class EditRefused(Exception):
    """The text cannot be edited as asked (it does not parse, or the path is not there)."""


# ---- reading ------------------------------------------------------------------------------------------------------
_BODY_OF: dict[int, str] = {}  # root node id -> its text, so `_walk` can check for aliases


def _root(body: str):
    node = locate(body)
    if node is None or not isinstance(node, yaml.MappingNode):
        raise EditRefused("the file cannot be read as a mapping of records, so it cannot be edited")
    _BODY_OF[id(node)] = body
    if len(_BODY_OF) > 32:
        _BODY_OF.pop(next(iter(_BODY_OF)))
    return node


def _is_blank_document(body: str) -> bool:
    """True for an empty file or one that holds only comments (what `cronicl init` writes)."""
    result = load_text(body)
    return result.error is None and isinstance(result.data, Mapping) and not result.data


def _key_text(node) -> str:
    return node.value


ALIAS_MESSAGE = "this record uses a YAML anchor or alias (& or *), which the editor does not change; edit it as text with Ctrl+E"


def _check_plain(node, body: str, seen: set, parent=None) -> None:
    """Refuse a record with aliases or anchors: editing through them would change another record."""
    if id(node) in seen:
        raise EditRefused(ALIAS_MESSAGE)
    seen.add(id(node))
    if parent is not None and not (parent.start_mark.index <= node.start_mark.index and node.end_mark.index <= parent.end_mark.index):
        raise EditRefused(ALIAS_MESSAGE)
    if body[node.start_mark.index:node.start_mark.index + 1] == "&":
        raise EditRefused(ALIAS_MESSAGE)
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            _check_plain(k, body, seen, node)
            _check_plain(v, body, seen, node)
    elif isinstance(node, yaml.SequenceNode):
        for v in node.value:
            _check_plain(v, body, seen, node)


def _find_record(root, key: str, *, body: str | None = None):
    wanted = _norm_key(key)
    for key_node, value_node in root.value:
        if _norm_key(key_node.value) == wanted:
            if body is not None:
                _check_plain(value_node, body, set())
            return key_node, value_node
    raise EditRefused(f"there is no record {key!r}")


def _norm_key(key: str) -> str:
    if "+" in key:
        a, b = (part.strip() for part in key.split("+", 1))
        return " + ".join(sorted((a, b)))
    return key.strip()


def _step(node, step):
    """The (key_node or None, value_node) for `step` inside a mapping (by key) or a sequence (by index); None if absent."""
    if isinstance(node, yaml.MappingNode) and isinstance(step, str):
        for key_node, value_node in node.value:
            if key_node.value == step:
                return key_node, value_node
    elif isinstance(node, yaml.SequenceNode) and isinstance(step, int) and 0 <= step < len(node.value):
        return None, node.value[step]
    return None


def _walk(root, path):
    """Walk `path`; return the list of (key_node, value_node) per step as far as it exists."""
    key_node, value_node = _find_record(root, path[0], body=_BODY_OF.get(id(root)))
    trail = [(key_node, value_node)]
    for step in path[1:]:
        found = _step(trail[-1][1], step)
        if found is None:
            break
        trail.append(found)
    return trail


def record_span(text: str, key: str) -> tuple[int, int] | None:
    """The character span (in `text`) of a whole record: its key line through its last line."""
    bom, body = _split_bom(text)
    try:
        root = _root(body)
        key_node, value_node = _find_record(root, key)
    except EditRefused:
        return None
    start = body.rfind("\n", 0, key_node.start_mark.index) + 1
    end = _last_line_end(body, value_node.end_mark.index if value_node.end_mark.index > key_node.end_mark.index else key_node.end_mark.index)
    return len(bom) + start, len(bom) + end


def record_data(text: str, key: str) -> dict:
    """The record as plain nested dicts, lists and strings (key order kept), for rewriting and the raw pane."""
    bom, body = _split_bom(text)
    result = load_text(body)
    if result.error or not isinstance(result.data, Mapping):
        raise EditRefused("the file cannot be read, so it cannot be edited")
    wanted = _norm_key(key)
    for k, v in result.data.items():
        if _norm_key(k) == wanted:
            return _plain(v) if isinstance(v, Mapping) else {}
    raise EditRefused(f"there is no record {key!r}")


def _plain(value):
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence):
        return [_plain(v) for v in value]
    return value


# ---- rendering ----------------------------------------------------------------------------------------------------
def _inline(value) -> str:
    """A value as flow YAML on one line."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{quote(str(k))}: {_inline(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_inline(v) for v in value) + "]"
    return quote(str(value))


def _entry(indent: str, key: str, value, nl: str) -> list[str]:
    """Lines for `key: value` as the canonical writer lays it out."""
    if isinstance(value, dict):
        if not value:
            return [f"{indent}{key}: {{}}"]
        if key in ("birth", "death") and list(value) == ["date"]:
            return [f"{indent}{key}: {quote(str(value['date']), flow=False)}"]
        one = f"{indent}{key}: {_inline(value)}"
        if len(one) <= LONG:
            return [one]
        return [f"{indent}{key}:"] + [line for k, v in value.items() for line in _entry(indent + "  ", k, v, nl)]
    if isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            lines = [f"{indent}{key}:"]
            for item in value:
                one = f"{indent}  - {_inline(item)}"
                if len(one) <= LONG + 20:
                    lines.append(one)
                else:
                    pairs = list(item.items())
                    lines.append(f"{indent}  - {pairs[0][0]}: {_inline(pairs[0][1])}")
                    lines += [f"{indent}    {k}: {_inline(v)}" for k, v in pairs[1:]]
            return lines
        return [f"{indent}{key}: {_inline(value)}"]
    text = str(value)
    if "\n" in text:
        return _literal(indent, key, text)
    return [f"{indent}{key}: {quote(text, flow=False)}"]


def _literal(indent: str, key: str, text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f  ﻿]", text) or any(line.endswith((" ", "\t")) for line in text.split("\n")):
        return [f"{indent}{key}: {quote(text)}"]
    head = "|" + ("2" if text[0] in " \t" else "")
    return [f"{indent}{key}: {head}"] + [f"{indent}  {line}" if line else "" for line in text.split("\n")]


def _order_for_record(key: str) -> tuple:
    return COUPLE_ORDER if "+" in key else PERSON_ORDER


def render_record(key_text: str, data: dict, nl: str = "\n") -> str:
    """One record in the canonical block layout (known keys in canonical order, the owner's own keys after them)."""
    if not data:
        return f"{key_text}: {{}}{nl}"
    order = _order_for_record(key_text)
    keys = [k for k in order if k in data] + [k for k in data if k not in order]
    lines = [f"{key_text}:"]
    for k in keys:
        lines += _entry("  ", k, data[k], nl)
    return nl.join(lines) + nl


# ---- applying edits -----------------------------------------------------------------------------------------------
def _splice(body: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, repl in sorted(edits, reverse=True):
        body = body[:start] + repl + body[end:]
    return body


def _line_start(body: str, index: int) -> int:
    return body.rfind("\n", 0, index) + 1


def _line_len(body: str, index: int) -> int:
    start = _line_start(body, index)
    end = body.find("\n", index)
    end = len(body) if end == -1 else end
    return len(body[start:end].rstrip("\r"))


def _scalar_span(body: str, node) -> tuple[int, int]:
    start, end = node.start_mark.index, node.end_mark.index
    if node.style in ("|", ">"):
        return start, start + len(body[start:end].rstrip(" \t\r\n"))
    return start, end


def _render_scalar(old_node, value: str, *, flow: bool, key_indent: int | None, nl: str) -> str:
    """A scalar's new text: keep the old quote style when the new value fits it, else the canonical quoting."""
    if "\n" in value and not flow:
        lines = _literal(" " * (key_indent or 0), "x", value)
        head = lines[0].split(": ", 1)[1]
        return nl.join([head] + lines[1:])
    if old_node is not None and old_node.style in ('"', "'") and value and not re.search(r"[\x00-\x1f\x7f\\\"'\n]", value):
        return f"{old_node.style}{value}{old_node.style}"
    return quote(value, flow=flow)


def _inside_flow(path_trail) -> bool:
    return any(isinstance(v, (yaml.MappingNode, yaml.SequenceNode)) and v.flow_style for _, v in path_trail[:-1])


def set_value(text: str, path: tuple, value: str) -> str:
    """Give the value at `path` the text `value`, in place; add the key (and a missing nested mapping) when absent."""
    try:
        return _set_value(text, path, value)
    except _NeedsRewrite as fallback:
        data = record_data(text, fallback.record)
        _set_plain(data, path[1:], value)
        return rewrite_record(text, fallback.record, data)


def _set_value(text: str, path: tuple, value: str) -> str:
    bom, body = _split_bom(text)
    root = _root(body)
    trail = _walk(root, path)
    nl = _newline(body)
    if len(trail) == len(path):
        node = trail[-1][1]
        if not isinstance(node, yaml.ScalarNode):
            raise EditRefused("that is not a single value; edit it by hand")
        if node.value == "" and node.start_mark.index == node.end_mark.index:
            return bom + _fill_blank(body, trail, value, nl)
        key_node = trail[-1][0]
        flow = _inside_flow(trail)
        indent = key_node.start_mark.column if key_node is not None else None
        start, end = _scalar_span(body, node)
        new = _render_scalar(node, value, flow=flow, key_indent=indent, nl=nl)
        if "\n" in new and node.style not in ("|", ">"):
            line_end = body.find("\n", end)
            line_end = len(body) if line_end == -1 else line_end
            tail = body[end:line_end].rstrip("\r")
            if tail.strip().startswith("#"):  # the comment stays a comment: it moves up beside the `|`
                first, _, rest = new.partition(nl)
                new = first + "  " + tail.strip() + (nl + rest if rest else "")
                end = end + len(tail)
        return bom + body[:start] + new + body[end:]
    missing = path[len(trail):]
    if any(isinstance(step, int) for step in missing):
        raise EditRefused("there is no such list item")
    parent_key, parent = trail[-1]
    if isinstance(parent, yaml.MappingNode):
        data: object = value
        for name in reversed(missing[1:]):
            data = {name: data}
        return bom + _insert_into(body, root, trail, path[: len(trail)], missing[0], data, nl)
    if isinstance(parent, yaml.ScalarNode):
        name = path[len(trail) - 1]
        if parent.value == "" and parent.start_mark.index == parent.end_mark.index:  # `birth:` with nothing after it
            data = value
            if not (name in ("birth", "death") and list(missing) == ["date"]):  # a lone date is written bare
                for step in reversed(missing):
                    data = {step: data}
            return bom + _fill_blank(body, trail, data, nl, key=name)
        if len(trail) >= 2 and name in ("birth", "death") and len(missing) == 1:  # a bare date becomes {date: .., key: ..}
            start, end = _scalar_span(body, parent)
            new = _inline({"date": body[start:end].strip("\"'"), missing[0]: value})
            return bom + _guard_long(body, text_start=start, text_end=end, new=new, root=root, path=path, value=value, bom=bom, original=text)
        raise EditRefused("that value has no parts to set")
    raise EditRefused("that part of the record cannot be edited here")


def _guard_long(body, *, text_start, text_end, new, root, path, value, bom, original):
    edited = body[:text_start] + new + body[text_end:]
    if _line_len(edited, text_start) > LONG:
        data = record_data(original, path[0])
        _set_plain(data, path[1:], value)
        return _rewrite(body, path[0], data)
    return edited


def _set_plain(data: dict, path: tuple, value) -> None:
    node = data
    for step in path[:-1]:
        if isinstance(node, dict) and step in node and isinstance(node[step], (dict, list)):
            node = node[step]
        elif isinstance(node, dict) and step in node and isinstance(node[step], str) and step in ("birth", "death"):
            node[step] = {"date": node[step]}
            node = node[step]
        elif isinstance(node, list) and isinstance(step, int):
            node = node[step]
        else:
            node[step] = {}
            node = node[step]
    last = path[-1]
    if isinstance(node, list) and isinstance(last, int):
        node[last] = value
    else:
        node[last] = value


def _fill_blank(body: str, trail, data, nl: str, key: str | None = None) -> str:
    """The value at the end of `trail` is blank (`key:`): write `data` there."""
    key_node, node = trail[-1]
    if key_node is None:
        raise EditRefused("that list item is empty")
    if isinstance(data, dict):
        # a blank record or nested mapping: block lines under the key
        at = _last_line_end(body, key_node.end_mark.index)
        indent = " " * (key_node.start_mark.column + 2)
        lines = []
        for k, v in data.items():
            lines += _entry(indent, k, v, nl)
        prefix = "" if body[:at].endswith("\n") or at == 0 else nl
        return body[:at] + prefix + nl.join(lines) + nl + body[at:]
    start = node.start_mark.index
    text = _render_scalar(None, data, flow=False, key_indent=key_node.start_mark.column, nl=nl)
    return body[:start] + (" " if body[start - 1:start] == ":" else "") + text + body[start:]


def _order_of(trail, path_len: int) -> tuple:
    """The canonical key order of the mapping the trail ends in."""
    if path_len == 1:
        return _order_for_record(trail[0][0].value)
    name = trail[path_len - 1][0]
    if name is not None and name.value in _NESTED_ORDER and path_len == 2:
        return _NESTED_ORDER[name.value]
    if len(trail) >= path_len and isinstance(trail[path_len - 1][1], yaml.MappingNode) and path_len >= 3 and trail[path_len - 2][0] is not None and trail[path_len - 2][0].value == "events":
        return EVENT_ORDER
    if path_len >= 2 and trail[path_len - 2][0] is not None and trail[path_len - 2][0].value == "events":
        return EVENT_ORDER
    return ()


def _insert_into(body: str, root, trail, parent_path, key: str, value, nl: str) -> str:
    mapping = trail[-1][1]
    order = _order_of(trail, len(parent_path))
    rank = order.index(key) if key in order else len(order)
    prev = None
    for child_key, child_value in mapping.value:
        child_rank = order.index(child_key.value) if child_key.value in order else len(order)
        if child_rank < rank or (child_rank == rank and child_key.value not in order):
            prev = (child_key, child_value)
    if mapping.flow_style:
        return _insert_flow(body, mapping, prev, key, value, parent_path)
    indent_col = mapping.value[0][0].start_mark.column if mapping.value else trail[-1][0].start_mark.column + 2
    lines = _entry(" " * indent_col, key, value, nl)
    if prev is not None:
        at = _last_line_end(body, prev[1].end_mark.index)
    elif mapping.value and body[_line_start(body, mapping.value[0][0].start_mark.index):mapping.value[0][0].start_mark.index].strip() == "":
        at = _line_start(body, mapping.value[0][0].start_mark.index)
    elif mapping.value:
        at = _last_line_end(body, mapping.value[0][1].end_mark.index)
    else:
        at = _last_line_end(body, trail[-1][0].end_mark.index)
    prefix = "" if at == 0 or body[at - 1] == "\n" else nl
    return body[:at] + prefix + nl.join(lines) + nl + body[at:]


def _insert_flow(body: str, mapping, prev, key: str, value, parent_path) -> str:
    entry = f"{quote(key)}: {_inline(value)}"
    start, end = mapping.start_mark.index, mapping.end_mark.index
    if not mapping.value:
        new = body[:start] + "{" + entry + "}" + body[end:]
    elif prev is not None:
        at = prev[1].end_mark.index
        new = body[:at] + ", " + entry + body[at:]
    else:
        at = mapping.value[0][0].start_mark.index
        new = body[:at] + entry + ", " + body[at:]
    if _line_len(new, start) > LONG:
        record = parent_path[0]
        raise _NeedsRewrite(record)
    return new


class _NeedsRewrite(Exception):
    def __init__(self, record: str):
        self.record = record


def _rewrite(body: str, record: str, data: dict) -> str:
    root = _root(body)
    key_node, value_node = _find_record(root, record)
    start = _line_start(body, key_node.start_mark.index)
    end = _last_line_end(body, value_node.end_mark.index if value_node.end_mark.index > key_node.end_mark.index else key_node.end_mark.index)
    key_text = body[key_node.start_mark.index:key_node.end_mark.index]
    return body[:start] + render_record(key_text, data, _newline(body)) + body[end:]


def rewrite_record(text: str, record: str, data: dict) -> str:
    """Replace one record with the canonical block layout of `data` (the fallback, and what the raw pane uses)."""
    bom, body = _split_bom(text)
    return bom + _rewrite(body, record, data)


def insert_key(text: str, record: str, key: str, value, *, under: tuple = ()) -> str:
    """Add `key` (a string, a dict for a nested mapping, or a list) to the record, or to the mapping at `under`."""
    return set_value_any(text, (record, *under, key), value)


def set_value_any(text: str, path: tuple, value) -> str:
    """`set_value` for values that are not plain text (a nested mapping, a list): adds the key where it belongs."""
    if isinstance(value, str):
        return set_value(text, path, value)
    bom, body = _split_bom(text)
    root = _root(body)
    trail = _walk(root, path[:-1])
    if len(trail) != len(path) - 1:
        raise EditRefused("that part of the record is not there")
    parent = trail[-1][1]
    if isinstance(parent, yaml.ScalarNode) and parent.value == "" and parent.start_mark.index == parent.end_mark.index and trail[-1][0] is not None:
        return bom + _fill_blank(body, trail, {path[-1]: value}, _newline(body))  # `ghost:` with nothing under it
    if _step(parent, path[-1]) is not None:
        raise EditRefused(f"{path[-1]!r} is already there")
    try:
        return bom + _insert_into(body, root, trail, path[:-1], path[-1], value, _newline(body))
    except _NeedsRewrite as fallback:
        data = record_data(text, fallback.record)
        _set_plain(data, path[1:], value)
        return rewrite_record(text, fallback.record, data)


# ---- removing -----------------------------------------------------------------------------------------------------
def remove(text: str, path: tuple) -> str:
    """Delete the key or list item at `path`; a nested mapping or list left empty goes with it."""
    try:
        return _remove(text, path)
    except _NeedsRewrite as fallback:
        data = record_data(text, fallback.record)
        _del_plain(data, path[1:])
        return rewrite_record(text, fallback.record, data)


def _del_plain(data, path: tuple) -> None:
    node = data
    for step in path[:-1]:
        node = node[step]
    del node[path[-1]]
    if not node and len(path) > 1:
        _del_plain(data, path[:-1])


def _remove(text: str, path: tuple) -> str:
    bom, body = _split_bom(text)
    root = _root(body)
    trail = _walk(root, path)
    if len(trail) != len(path):
        raise EditRefused("that is not in the record")
    if len(path) == 1:
        raise EditRefused("a whole record is removed by the caller")
    parent = trail[-2][1]
    key_node, value_node = trail[-1]
    nl = _newline(body)
    count = len(parent.value)
    if count == 1 and len(path) > 2:
        return bom + _remove_text(body, root, path[:-1], nl)  # the last part of a nested value: remove the whole value
    return bom + _remove_one(body, parent, key_node, value_node, path, nl)


def _remove_text(body: str, root, path: tuple, nl: str) -> str:
    trail = _walk(root, path)
    parent = trail[-2][1]
    return _remove_one(body, parent, trail[-1][0], trail[-1][1], path, nl)


def _remove_one(body: str, parent, key_node, value_node, path: tuple, nl: str) -> str:
    entries = parent.value
    if isinstance(parent, yaml.SequenceNode):
        index = path[-1]
        if parent.flow_style:
            return _remove_flow(body, parent, [(None, v) for v in entries], index)
        item = value_node
        start = _line_start(body, item.start_mark.index)
        dash = body.rfind("-", start, item.start_mark.index)
        end = _last_line_end(body, item.end_mark.index)
        return body[:start] + body[end:]
    index = next(i for i, (k, _) in enumerate(entries) if k is key_node)
    if parent.flow_style:
        return _remove_flow(body, parent, entries, index)
    first_on_line = body[_line_start(body, key_node.start_mark.index):key_node.start_mark.index].strip() != ""
    if first_on_line:
        raise _NeedsRewrite(path[0])
    start = _line_start(body, key_node.start_mark.index)
    end = _last_line_end(body, value_node.end_mark.index if value_node.end_mark.index > key_node.end_mark.index else key_node.end_mark.index)
    return body[:start] + body[end:]


def _remove_flow(body: str, parent, entries, index: int) -> str:
    def span(i):
        k, v = entries[i]
        return (k.start_mark.index if k is not None else v.start_mark.index), v.end_mark.index

    start, end = span(index)
    if len(entries) == 1:
        return body[: parent.start_mark.index + 1] + body[parent.end_mark.index - 1:]
    if index + 1 < len(entries):
        nxt = span(index + 1)[0]
        return body[:start] + body[nxt:]
    prev_end = span(index - 1)[1]
    return body[:prev_end] + body[end:]


# ---- lists --------------------------------------------------------------------------------------------------------
def record_text(text: str, key: str) -> str:
    """The record's own lines, as the raw pane shows them."""
    span = record_span(text, key)
    if span is None:
        raise EditRefused(f"there is no record {key!r}")
    return text[span[0]:span[1]]


def _item_flow(item) -> str:
    return _inline(item) if isinstance(item, (dict, list)) else quote(str(item))


def list_add(text: str, path: tuple, item) -> str:
    """Append `item` (text for `parents`, a dict for `events`) to the list at `path`, creating the list when absent."""
    try:
        return _list_add(text, path, item)
    except _NeedsRewrite as fallback:
        data = record_data(text, fallback.record)
        node = data
        for step in path[1:-1]:
            node = node[step]
        node.setdefault(path[-1], []).append(item)
        return rewrite_record(text, fallback.record, data)


def _list_add(text: str, path: tuple, item) -> str:
    bom, body = _split_bom(text)
    root = _root(body)
    trail = _walk(root, path)
    if len(trail) < len(path):
        return set_value_any(text, path, [item])
    key_node, node = trail[-1]
    nl = _newline(body)
    if isinstance(node, yaml.ScalarNode) and node.value == "":
        return list_add(remove(text, path), path, item)
    if not isinstance(node, yaml.SequenceNode):
        raise EditRefused(f"{path[-1]} is not a list")
    if node.flow_style:
        start, end = node.start_mark.index, node.end_mark.index
        if not node.value:
            new = body[:start] + "[" + _item_flow(item) + "]" + body[end:]
        else:
            at = node.value[-1].end_mark.index
            new = body[:at] + ", " + _item_flow(item) + body[at:]
        if _line_len(new, start) > LONG:
            raise _NeedsRewrite(path[0])
        return bom + new
    first = node.value[0]
    line_start = _line_start(body, first.start_mark.index)
    dash_col = len(body[line_start:first.start_mark.index]) - len(body[line_start:first.start_mark.index].lstrip())
    rendered = _inline(item) if isinstance(item, (dict, list)) else quote(str(item), flow=False)
    at = _last_line_end(body, node.value[-1].end_mark.index)
    prefix = "" if at == 0 or body[at - 1] == "\n" else nl
    return bom + body[:at] + prefix + " " * dash_col + "- " + rendered + nl + body[at:]


def list_remove(text: str, path: tuple, index: int) -> str:
    """Remove item `index` of the list at `path`; the last item takes the list's key with it."""
    return remove(text, (*path, index))


def list_replace(text: str, path: tuple, index: int, item) -> str:
    """Give list item `index` the value `item` (text, or a dict written as a flow mapping)."""
    if isinstance(item, str):
        return set_value(text, (*path, index), item)
    bom, body = _split_bom(text)
    trail = _walk(_root(body), (*path, index))
    if len(trail) != len(path) + 1:
        raise EditRefused("there is no such list item")
    node = trail[-1][1]
    start = node.start_mark.index
    end = node.end_mark.index if node.flow_style else start + len(body[start:_last_line_end(body, node.end_mark.index)].rstrip("\r\n"))
    new = body[:start] + _inline(item) + body[end:]
    if _line_len(new, start) > LONG + 20:
        data = record_data(text, path[0])
        target = data
        for step in path[1:]:
            target = target[step]
        target[index] = item
        return rewrite_record(text, path[0], data)
    return bom + new


# ---- couples and whole records ------------------------------------------------------------------------------------
def couple_key(a: str, b: str) -> str:
    first, second = sorted((a, b))
    return f"{first} + {second}"


def _find_couple(text: str, a: str, b: str):
    """The couple's key (normalised, so it finds `'b  +  a'` too) when the file has a record for them, else None."""
    bom, body = _split_bom(text)
    if not body.strip() or _is_blank_document(body):
        return None
    wanted = couple_key(a, b)
    for key_node, _ in _root(body).value:
        if _norm_key(key_node.value) == wanted:
            return wanted
    return None


def _append_block(text: str, block_key: str, data: dict) -> str:
    nl = "\r\n" if "\r\n" in text else "\n"
    block = render_record(block_key, data, nl)
    if not text.strip():
        return block
    base = text if text.endswith("\n") else text + nl
    return base + nl + block


def add_person_record(text: str, key: str, data: dict) -> str:
    """Append a new person record (canonical layout) at the end, after a blank line."""
    bom, body = _split_bom(text)
    if _has_key(body, key):
        raise EditRefused(f"{key!r} is already in the file")
    return bom + _append_block(body, key, data)


def _has_key(body: str, key: str) -> bool:
    if not body.strip() or _is_blank_document(body):
        return False
    root = _root(body)
    return any(_norm_key(k.value) == _norm_key(key) for k, _ in root.value)


def add_couple_record(text: str, a: str, b: str, events=(), note: str | None = None) -> str:
    """Add the couple record `a + b` directly after its second partner's record (at the end if that is elsewhere)."""
    bom, body = _split_bom(text)
    if _find_couple(body, a, b) is not None:
        raise EditRefused(f"{couple_key(a, b)} is already in the file")
    data: dict = {}
    if events:
        data["events"] = list(events)
    if note:
        data["note"] = note
    key = couple_key(a, b)
    second = sorted((a, b))[1]
    span = record_span(body, second) if _has_key(body, second) else None
    if span is None:
        return bom + _append_block(body, key, data)
    nl = _newline(body)
    block = render_record(key, data, nl)
    end = span[1]
    prefix = "" if end == 0 or body[end - 1] == "\n" else nl
    return bom + body[:end] + prefix + nl + block + body[end:]


def add_couple_event(text: str, a: str, b: str, event: dict) -> str:
    """Add an event to the couple's record, creating the record when there is none."""
    existing = _find_couple(text, a, b)
    if existing is None:
        return add_couple_record(text, a, b, [event])
    return list_add(text, (existing, "events"), event)


def replace_record(text: str, key: str, raw: str) -> str:
    """Replace a record by `raw`, which must parse as exactly that one record."""
    result = load_text(raw)
    if result.error or not isinstance(result.data, Mapping) or len(result.data) != 1:
        raise EditRefused(result.error or "the text must be exactly one record")
    (new_key,) = result.data.keys()
    if _norm_key(new_key) != _norm_key(key):
        raise EditRefused(f"the record key must stay {key!r} (it is {new_key!r})")
    span = record_span(text, key)
    if span is None:
        raise EditRefused(f"there is no record {key!r}")
    nl = "\r\n" if "\r\n" in text else "\n"
    block = raw.replace("\r\n", "\n").rstrip("\n").replace("\n", nl) + nl
    return text[: span[0]] + block + text[span[1]:]


# ---- locating and renaming ----------------------------------------------------------------------------------------
def paths_at_line(text: str, line: int) -> list[tuple]:
    """Every path whose key (or list item) starts on file line `line` (1-based), outermost first."""
    bom, body = _split_bom(text)
    found: list[tuple] = []

    def visit(node, path):
        if isinstance(node, yaml.MappingNode):
            for key_node, value in node.value:
                here = (*path, key_node.value)
                if key_node.start_mark.line + 1 == line:
                    found.append(here)
                visit(value, here)
        elif isinstance(node, yaml.SequenceNode):
            for index, item in enumerate(node.value):
                here = (*path, index)
                if item.start_mark.line + 1 == line:
                    found.append(here)
                visit(item, here)

    try:
        root = _root(body)
    except EditRefused:
        return []
    visit(root, ())
    return found


def rename_key(text: str, path: tuple, new: str) -> str:
    """Give the key at `path` a new name (a misspelling fixed), in place."""
    bom, body = _split_bom(text)
    trail = _walk(_root(body), path)
    if len(trail) != len(path) or trail[-1][0] is None:
        raise EditRefused("that key is not in the record")
    key_node = trail[-1][0]
    return bom + body[: key_node.start_mark.index] + quote(new) + body[key_node.end_mark.index:]
