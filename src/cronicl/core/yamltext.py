"""Reading YAML the way a family file needs: every value is text, every key knows its line.

What it gives that plain YAML loaders do not:

- every scalar stays text, exactly as typed (`NO`, `1066`, `0123`), and an empty value is `""`;
- mappings and sequences remember the line of each key or item, for error messages;
- a key repeated in one mapping, and a merge key (`<<`), are reported instead of silently honoured;
- a bad file is a result with an `error`, never an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml


class Mapping(dict):
    """A mapping of text to values that remembers where each key was written (1-based lines)."""

    lines: dict
    line: int

    def __init__(self):
        super().__init__()
        self.lines = {}
        self.line = 0


class Sequence(list):
    lines: list

    def __init__(self):
        super().__init__()
        self.lines = []


@dataclass
class LoadResult:
    data: object = None
    duplicates: list = field(default_factory=list)  # (key, line of the repeat)
    merge_keys: list = field(default_factory=list)  # lines
    error: str | None = None
    error_line: int | None = None


class _Loader(yaml.BaseLoader):
    def __init__(self, stream):
        super().__init__(stream)
        self.duplicates: list = []
        self.merge_keys: list = []

    def construct_mapping(self, node, deep=False):
        out = Mapping()
        out.line = node.value[0][0].start_mark.line + 1 if node.value else node.start_mark.line + 1
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            line = key_node.start_mark.line + 1
            try:
                hash(key)
            except TypeError:
                raise yaml.constructor.ConstructorError(
                    None, None, "found a list or mapping used as a key", key_node.start_mark
                ) from None
            if key == "<<":
                self.merge_keys.append(line)
            if key in out:
                self.duplicates.append((key, line))
            out[key] = self.construct_object(value_node, deep=deep)
            out.lines[key] = line
        return out

    def construct_sequence(self, node, deep=False):
        out = Sequence()
        for child in node.value:
            out.append(self.construct_object(child, deep=deep))
            out.lines.append(child.start_mark.line + 1)
        return out


def load_text(raw: str) -> LoadResult:
    """Parse `raw`. Never raises: a problem is reported in `error` (with `error_line` when YAML says where)."""
    result = LoadResult()
    text = raw.lstrip("﻿") if isinstance(raw, str) else raw
    loader = None
    try:
        loader = _Loader(text)
        data = loader.get_single_data()
        result.data = Mapping() if data is None or data == "" else data
        result.duplicates = loader.duplicates
        result.merge_keys = loader.merge_keys
    except yaml.YAMLError as exc:
        result.error = " ".join(str(exc).split())
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        if mark is not None:
            result.error_line = mark.line + 1
    except (RecursionError, ValueError, TypeError, UnicodeError, MemoryError) as exc:
        result.error = f"cannot read this text: {type(exc).__name__}"
    finally:
        if loader is not None:
            loader.dispose()
    if result.error is not None:
        result.data = None
    return result


def locate(raw: str):
    """The parsed node graph, with exact positions (`start_mark.index` / `end_mark.index`) for in-place edits.

    Returns None when the text cannot be read.
    """
    text = raw.lstrip("﻿")
    try:
        return yaml.compose(text, Loader=yaml.BaseLoader)
    except (yaml.YAMLError, RecursionError, ValueError, TypeError):
        return None
