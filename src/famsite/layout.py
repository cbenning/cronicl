from __future__ import annotations

from .model import Tree
from .relations import build_relations

NODE_W = 160
NODE_H = 56
H_GAP = 24
BLOCK_GAP = 56
ROW_GAP = 84
MARGIN = 32
SWEEPS = 4


class LayoutError(Exception):
    """The tree cannot be laid out (for example, it contains an ancestry cycle)."""


def _num(value: float):
    value = round(float(value), 2)
    return int(value) if value.is_integer() else value


def _generations(people, unions, kids) -> dict[str, int]:
    gen = {pid: 0 for pid in people}
    for _ in range(len(people) + len(unions) + 2):
        changed = False
        for uid in sorted(unions):
            members = unions[uid]
            row = max(gen[p] for p in members)
            for pid in members:
                if gen[pid] != row:
                    gen[pid] = row
                    changed = True
            for kid in kids[uid]:
                if gen[kid] < row + 1:
                    gen[kid] = row + 1
                    changed = True
        if not changed:
            return gen
    raise LayoutError("could not assign generations; the tree probably contains an ancestry cycle")


def _order_component(component: list[str], adj: dict[str, set[str]]) -> list[str]:
    start = min(component, key=lambda n: (len(adj[n]), n))
    order: list[str] = []
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        order.append(node)
        for other in sorted(adj[node], reverse=True):
            if other not in seen:
                stack.append(other)
    return order


def _blocks(people: list[str], unions: dict[str, list[str]]) -> list[list[str]]:
    adj: dict[str, set[str]] = {pid: set() for pid in people}
    for members in unions.values():
        for a in members:
            for b in members:
                if a != b:
                    adj[a].add(b)
    seen: set[str] = set()
    blocks: list[list[str]] = []
    for pid in people:
        if pid in seen:
            continue
        component: list[str] = []
        stack = [pid]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.append(node)
            stack.extend(m for m in adj[node] if m not in seen)
        blocks.append(_order_component(component, adj))
    return blocks


def _family_labels(people, unions, parent_union) -> dict[str, str]:
    parent = {p: p for p in people}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for members in unions.values():
        for other in members[1:]:
            join(members[0], other)
    for pid, uid in parent_union.items():
        join(pid, unions[uid][0])
    return {p: find(p) for p in people}


def _pack(order: list[int], desired: dict[int, float | None], widths: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = {}
    cursor: float | None = None
    for block in order:
        want = desired.get(block)
        left = None if want is None else want - widths[block] / 2
        if cursor is None:
            out[block] = left if left is not None else float(MARGIN)
        else:
            floor = cursor + BLOCK_GAP
            out[block] = max(left, floor) if left is not None else floor
        cursor = out[block] + widths[block]
    return out


def compute_layout(tree: Tree) -> dict:
    relations = build_relations(tree)
    people = sorted(tree.people)
    unions = {cid: list(couple.partners) for cid, couple in sorted(relations.couples.items())}
    kids = {cid: list(relations.kids.get(cid, [])) for cid in unions}
    parent_union = dict(relations.birth_couple)

    if not people:
        return {
            "version": 1,
            "bounds": {"w": 2 * MARGIN, "h": 2 * MARGIN},
            "nodes": [],
            "unions": [],
            "edges": [],
        }

    gen = _generations(people, unions, kids)
    blocks = _blocks(people, unions)
    block_of = {pid: i for i, members in enumerate(blocks) for pid in members}
    labels = _family_labels(people, unions, parent_union)
    widths = {i: len(m) * NODE_W + (len(m) - 1) * H_GAP for i, m in enumerate(blocks)}
    block_gen = {i: gen[m[0]] for i, m in enumerate(blocks)}

    rows: dict[int, list[int]] = {}
    for index in range(len(blocks)):
        rows.setdefault(block_gen[index], []).append(index)
    for g in rows:
        rows[g].sort(key=lambda b: (labels[blocks[b][0]], min(blocks[b]), b))

    xl: dict[int, float] = {}
    for g in sorted(rows):
        xl.update(_pack(rows[g], {}, widths))

    def center(pid: str) -> float:
        b = block_of[pid]
        return xl[b] + blocks[b].index(pid) * (NODE_W + H_GAP) + NODE_W / 2

    def junction_x(uid: str) -> float:
        members = unions[uid]
        return sum(center(p) for p in members) / len(members)

    def block_center(b: int) -> float:
        return xl[b] + widths[b] / 2

    def down_sweep() -> None:
        for g in sorted(rows):
            desired: dict[int, float | None] = {}
            for b in rows[g]:
                xs = [junction_x(parent_union[p]) for p in blocks[b] if p in parent_union]
                desired[b] = sum(xs) / len(xs) if xs else None
            order = sorted(
                rows[g],
                key=lambda b: (desired[b] if desired[b] is not None else block_center(b), min(blocks[b])),
            )
            xl.update(_pack(order, desired, widths))
            rows[g] = order

    def up_sweep() -> None:
        for g in sorted(rows, reverse=True):
            desired: dict[int, float | None] = {}
            for b in rows[g]:
                xs: list[float] = []
                for pid in blocks[b]:
                    for uid in relations.couples_of.get(pid, []):
                        xs.extend(center(k) for k in kids[uid])
                desired[b] = sum(xs) / len(xs) if xs else None
            order = sorted(
                rows[g],
                key=lambda b: (desired[b] if desired[b] is not None else block_center(b), min(blocks[b])),
            )
            xl.update(_pack(order, desired, widths))
            rows[g] = order

    for _ in range(SWEEPS):
        down_sweep()
        up_sweep()
    down_sweep()

    shift = MARGIN - min(xl.values())
    for b in xl:
        xl[b] += shift

    def row_y(g: int) -> float:
        return MARGIN + g * (NODE_H + ROW_GAP)

    nodes = [
        {"id": pid, "x": _num(center(pid) - NODE_W / 2), "y": _num(row_y(gen[pid])), "w": NODE_W, "h": NODE_H}
        for pid in people
    ]
    out_unions = []
    edges = []
    for uid, members in unions.items():
        jx = junction_x(uid)
        g = gen[members[0]]
        multi = len(members) >= 2
        jy = row_y(g) + (NODE_H / 2 if multi else NODE_H)
        out_unions.append({"id": uid, "x": _num(jx), "y": _num(jy)})
        if multi:
            for pid in members:
                c = center(pid)
                edge_x = c + NODE_W / 2 if c < jx else c - NODE_W / 2
                edges.append(
                    {"from": pid, "to": uid, "kind": "spouse", "points": [[_num(edge_x), _num(jy)], [_num(jx), _num(jy)]]}
                )
        mid = row_y(g) + NODE_H + ROW_GAP / 2
        for kid in kids[uid]:
            kx = center(kid)
            ky = row_y(gen[kid])
            edges.append(
                {
                    "from": uid,
                    "to": kid,
                    "kind": "child",
                    "points": [[_num(jx), _num(jy)], [_num(jx), _num(mid)], [_num(kx), _num(mid)], [_num(kx), _num(ky)]],
                }
            )
    edges.sort(key=lambda e: (e["from"], e["to"], e["kind"]))
    width = max(n["x"] + n["w"] for n in nodes) + MARGIN
    height = max(n["y"] + n["h"] for n in nodes) + MARGIN
    return {
        "version": 1,
        "bounds": {"w": _num(width), "h": _num(height)},
        "nodes": nodes,
        "unions": out_unions,
        "edges": edges,
    }
