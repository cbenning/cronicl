"""A small structural validator for GEDCOM text, used by the export tests."""
import re

LINE = re.compile(r"^(\d+) (?:(@[A-Za-z0-9_]+@) )?([A-Z_0-9]+)(?: (.*))?$")
POINTER = re.compile(r"^@[A-Za-z0-9_]+@$")


def problems(text: str) -> list[str]:
    out: list[str] = []
    xrefs: set[str] = set()
    pointers: list[tuple[int, str]] = []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    previous = -1
    for number, raw in enumerate(lines, 1):
        if len(raw) > 255:
            out.append(f"line {number}: {len(raw)} characters")
        match = LINE.match(raw)
        if not match:
            out.append(f"line {number}: cannot parse {raw[:40]!r}")
            continue
        level, xref, tag, value = int(match.group(1)), match.group(2), match.group(3), match.group(4) or ""
        if level > previous + 1:
            out.append(f"line {number}: level jumps from {previous} to {level}")
        previous = level
        if xref:
            if xref in xrefs:
                out.append(f"line {number}: duplicate xref {xref}")
            xrefs.add(xref)
        if level > 0 and tag in ("FAMC", "FAMS", "HUSB", "WIFE", "CHIL", "SUBM") or (tag == "SOUR" and value.startswith("@") and level > 0):
            if POINTER.match(value):
                pointers.append((number, value))
            else:
                out.append(f"line {number}: {tag} value {value!r} is not a pointer")
        elif "@" in value and not re.search(r"@@", value):
            out.append(f"line {number}: lone @ in {value[:30]!r}")
    for number, value in pointers:
        if value not in xrefs:
            out.append(f"line {number}: pointer {value} resolves to nothing")
    if not lines or lines[0] != "0 HEAD" or lines[-1] != "0 TRLR":
        out.append("must start with 0 HEAD and end with 0 TRLR")
    return out
