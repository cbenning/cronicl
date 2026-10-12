from __future__ import annotations

import re
from pathlib import Path

from .store import load_tree

_LIVING_LINE = re.compile(r"living:(\s|$)")


class EditError(Exception):
    """An edit command cannot be applied."""


def set_living_in_text(text: str, value: bool) -> str:
    """Set the top-level `living:` key in a person file's frontmatter, touching nothing else."""
    newline = "\r\n" if "\r\n" in text else "\n"
    bom = "﻿" if text.startswith("﻿") else ""
    body = text[len(bom):]
    line = f"living: {'true' if value else 'false'}"
    lines = body.split(newline)
    if lines and lines[0].rstrip() == "---":
        for end in range(1, len(lines)):
            if lines[end].rstrip() == "---":
                for index in range(1, end):
                    if _LIVING_LINE.match(lines[index]):  # column 0 only: block-scalar content is indented
                        lines[index] = line
                        break
                else:
                    lines.insert(end, line)
                return bom + newline.join(lines)
    return bom + f"---{newline}{line}{newline}---{newline}" + body


def apply_living(
    data_dir: Path, ids: list[str], value: bool, dry_run: bool = False
) -> list[tuple[Path, bool]]:
    """Set `living` on the named people. All ids are validated before anything is written."""
    tree, _ = load_tree(Path(data_dir))
    unknown = [pid for pid in ids if pid not in tree.people]
    if unknown:
        raise EditError("unknown person id(s): " + ", ".join(unknown) + "; use `famsite search` to find ids")
    results: list[tuple[Path, bool]] = []
    seen: set[str] = set()
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        path = tree.people[pid].path
        text = path.read_bytes().decode("utf-8")
        updated = set_living_in_text(text, value)
        changed = updated != text
        if changed and not dry_run:
            path.write_bytes(updated.encode("utf-8"))
        results.append((path, changed))
    return results
