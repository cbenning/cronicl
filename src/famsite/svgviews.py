from __future__ import annotations

import html
import math
from collections.abc import Callable

NAME_WIDTH = 20  # characters per name line; a 160px node at 13px text leaves room for about 20
_TYPE_CLASS = {"birth": "birth", "death": "death", "marriage": "marriage", "partnership": "marriage", "divorce": "divorce"}
_STEPS = (1, 2, 5, 10, 25, 50, 100)


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def wrap_name(text: str, width: int = NAME_WIDTH, lines: int = 2) -> list[str]:
    """Greedy word wrap to `lines` lines of at most `width` characters; the last line ends with an ellipsis if cut."""
    words = text.split()
    if not words:
        return [""]
    out: list[str] = []
    current = ""
    truncated = False
    for word in words:
        if len(word) > width:
            word = word[: width - 1] + "…"  # a single word wider than the box is hard-cut
            truncated = True
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        out.append(current)
        current = word
        if len(out) == lines:  # one more line would be needed
            truncated = True
            current = ""
            break
    if current and len(out) < lines:
        out.append(current)
    if truncated and not out[-1].endswith("…"):
        last = out[-1]
        out[-1] = (last if len(last) < width else last[: width - 1]) + "…"
    return out


def _year_position(row: dict) -> float:
    month, day = row.get("month"), row.get("day")
    if month:
        return row["year"] + (month - 1) / 12 + ((day or 1) - 1) / 372
    return row["year"] + 0.5


def lifeline_svg(rows: list[dict], href: str, label: str) -> str:
    """A one-row timeline of a person's life: own events filled, relatives' hollow; omitted below two dated events."""
    dated = [r for r in rows if r.get("year") is not None]
    if len(dated) < 2:
        return ""
    low = math.floor(min(r["year"] for r in dated))
    high = max(r["year"] for r in dated) + 1
    span = max(high - low, 1)
    step = next((s for s in _STEPS if span / s <= 8), _STEPS[-1])
    width, pad, axis_y = 720, 28, 38
    usable = width - 2 * pad

    def x_of(year: float) -> float:
        return round(pad + (year - low) / span * usable, 1)

    parts = [
        f'<a class="lifeline-link" href="{_esc(href)}">',
        f'<svg class="lifeline" role="img" aria-label="Lifeline of {_esc(label)}" '
        f'viewBox="0 0 {width} 64" width="100%" preserveAspectRatio="xMidYMid meet">',
        f'<line class="axis" x1="{pad}" x2="{width - pad}" y1="{axis_y}" y2="{axis_y}"/>',
    ]
    tick = math.ceil(low / step) * step
    while tick <= high:
        x = x_of(tick)
        parts.append(f'<line class="tick" x1="{x}" x2="{x}" y1="{axis_y - 4}" y2="{axis_y + 4}"/>')
        parts.append(f'<text class="tick-label" x="{x}" y="{axis_y + 20}" text-anchor="middle">{tick}</text>')
        tick += step
    for r in dated:
        css = _TYPE_CLASS.get(r["type"], "other")
        side = "self" if r.get("role") == "self" else "rel"
        title = f'{r["year"]} · {r["text"]}'
        parts.append(
            f'<circle class="mk {css} {side}" cx="{x_of(_year_position(r))}" cy="{axis_y}" r="6">'
            f"<title>{_esc(title)}</title></circle>"
        )
    parts.append("</svg></a>")
    return "".join(parts)


def tree_svg(
    layout: dict, people: dict[str, dict], current: str, href_for: Callable[[str], str], label: str
) -> str:
    """The person's focus layout as a static inline SVG whose nodes are links; omitted for a lone person."""
    nodes = layout["nodes"]
    if len(nodes) < 2:
        return ""
    ended = {u["id"] for u in layout["unions"] if u.get("ended")}
    width, height = layout["bounds"]["w"], layout["bounds"]["h"]
    parts = [
        f'<svg class="mini-tree" role="group" aria-label="{_esc(label)}" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
    ]
    for edge in layout["edges"]:
        css = f'edge {edge["kind"]}'
        if edge["kind"] == "spouse" and edge["to"] in ended:
            css += " ended"
        points = " ".join(f"{x},{y}" for x, y in edge["points"])
        parts.append(f'<polyline class="{css}" points="{points}" fill="none"/>')
    for union in layout["unions"]:
        css = "union ended" if union.get("ended") else "union"
        parts.append(f'<circle class="{css}" cx="{union["x"]}" cy="{union["y"]}" r="3"/>')
    for node in nodes:
        info = people.get(node["id"], {"name": node["id"], "years": ""})
        lines = wrap_name(info["name"])
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        cls = "node current" if node["id"] == current else "node"
        parts.append(f'<a href="{_esc(href_for(node["id"]))}"><g class="{cls}">')
        parts.append(f"<title>{_esc(info['name'])}</title>")
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        first = y + (26 if len(lines) == 1 else 22)
        text = f'<text class="name" x="{x + w / 2}" y="{first}" text-anchor="middle">'
        for i, line in enumerate(lines):
            text += f'<tspan x="{x + w / 2}" dy="{0 if i == 0 else 15}">{_esc(line)}</tspan>'
        parts.append(text + "</text>")
        if info.get("years"):
            parts.append(
                f'<text class="years" x="{x + w / 2}" y="{y + h - 10}" text-anchor="middle">{_esc(info["years"])}</text>'
            )
        parts.append("</g></a>")
    parts.append("</svg>")
    return "".join(parts)
