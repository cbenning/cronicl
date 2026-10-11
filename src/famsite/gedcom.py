from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field

from .issues import Issue


class GedcomError(Exception):
    """The GEDCOM file cannot be read."""


@dataclass
class Node:
    level: int
    tag: str
    value: str = ""
    xref: str | None = None
    children: list["Node"] = field(default_factory=list)


_LINE = re.compile(r"^\s*(\d+)\s+(?:(@[^@\s]+@)\s+)?(\S+)(?:\s(.*))?$")
_CHAR = re.compile(r"^\s*1\s+CHAR\s+(\S+)", re.M | re.I)


def decode_gedcom(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="strict")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    head = data[:4096].decode("ascii", errors="ignore")
    match = _CHAR.search(head)
    charset = match.group(1).upper() if match else "UTF-8"
    try:
        if charset in ("UTF-8", "UTF8"):
            return data.decode("utf-8")
        if charset in ("ASCII", "ANSI", "WINDOWS-1252", "CP1252", "IBM WINDOWS", "IBM-WINDOWS"):
            return data.decode("cp1252", errors="replace")
        if charset in ("UNICODE", "UTF-16"):
            return data.decode("utf-16")
    except UnicodeDecodeError as exc:
        raise GedcomError(f"file is not valid {charset}: {exc}") from exc
    if charset == "ANSEL":
        raise GedcomError("ANSEL encoding is not supported; re-export the file as UTF-8")
    raise GedcomError(f"unsupported character set {charset!r}")


def parse_nodes(text: str) -> tuple[list[Node], list[Issue]]:
    roots: list[Node] = []
    issues: list[Issue] = []
    stack: list[Node] = []
    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        if not raw.strip():
            continue
        match = _LINE.match(raw)
        if not match:
            issues.append(Issue("W-GEDCOM-LINE", f"line {number}: cannot parse {raw[:40]!r}"))
            continue
        level = int(match.group(1))
        xref, tag, value = match.group(2), match.group(3), match.group(4) or ""
        while stack and stack[-1].level >= level:
            stack.pop()
        if level == 0:
            node = Node(0, tag.upper(), value, xref)
            roots.append(node)
            stack = [node]
            continue
        if not stack:
            raise GedcomError(f"line {number}: content appears before the first level-0 record")
        parent = stack[-1]
        if level != parent.level + 1:
            issues.append(Issue("W-GEDCOM-LEVEL", f"line {number}: level jumps from {parent.level} to {level}"))
        upper = tag.upper()
        if upper == "CONT":
            parent.value += "\n" + value
            continue
        if upper == "CONC":
            parent.value += value
            continue
        node = Node(level, upper, value, xref)
        parent.children.append(node)
        stack.append(node)
    return roots, issues
