from __future__ import annotations

import dataclasses

from .model import Tree
from .relations import build_relations

NODE_W = 160
NODE_H = 64
H_GAP = 24
BLOCK_GAP = 56
ROW_GAP = 84
MARGIN = 32
SWEEPS = 4
BUS_PAD = 8  # minimum horizontal clearance between two buses on one level
BUS_STEP = 10  # vertical distance between bus levels
BUS_EDGE = 18  # clearance between a row of boxes and its first/last bus level
DROP_CLEAR = 8  # a vertical connector keeps at least this far from the side of a box it passes
ENTRY_INSET = 14  # a connector may enter a child's box anywhere except this close to a corner
JOG_EDGE = 14  # a detoured connector runs this far above the top of the child's box


class LayoutError(Exception):
    """The tree cannot be laid out (for example, it contains an ancestry cycle)."""


def _num(value: float):
    value = round(float(value), 2)
    return int(value) if value.is_integer() else value


def _clear_entry(blocked: list[tuple[float, float]], want: float) -> float | None:
    """The x nearest `want` (within the child's box, off its corners) where a vertical drop misses every blocked box."""
    reach = NODE_W / 2 - ENTRY_INSET
    offsets = [0.0]
    step = 8.0
    while step <= reach:
        offsets += [step, -step]
        step += 8.0
    for off in offsets:
        x = want + off
        if all(not (x0 - DROP_CLEAR < x < x1 + DROP_CLEAR) for x0, x1 in blocked):
            return x
    return None


def _nearest_free_column(blocked: list[tuple[float, float]], want: float) -> float:
    """The x nearest `want` that is clear of every blocked box, to detour a drop through the gaps between them."""
    spans = sorted((x0 - DROP_CLEAR, x1 + DROP_CLEAR) for x0, x1 in blocked)
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    candidates = [min(want, merged[0][0])]  # left of everything
    candidates.append(max(want, merged[-1][1]))  # right of everything
    for (_, left_end), (right_start, _) in zip(merged, merged[1:]):
        candidates.append(min(max(want, left_end), right_start))
    return min(candidates, key=lambda x: abs(x - want))


def _sibling_groups(unions, kids) -> dict[str, list[str]]:
    """For every person, all their children across couples: full and half siblings share a row."""
    by_parent: dict[str, set[str]] = {}
    for uid, members in unions.items():
        for pid in members:
            by_parent.setdefault(pid, set()).update(kids[uid])
    return {pid: sorted(children) for pid, children in sorted(by_parent.items()) if len(children) > 1}


def _generation_pass(gen, unions, kids, siblings) -> set[str]:
    """One relaxation pass; returns the couples (or sibling groups) that moved."""
    moved: set[str] = set()
    for uid in sorted(unions):
        members = unions[uid]
        row = max(gen[p] for p in members)
        for pid in members:
            if gen[pid] != row:
                gen[pid] = row
                moved.add(uid)
        for kid in kids[uid]:
            if gen[kid] < row + 1:
                gen[kid] = row + 1
                moved.add(uid)
    for parent, children in siblings.items():
        deepest = max(gen[c] for c in children)
        for child in children:
            if gen[child] != deepest:
                gen[child] = deepest
                moved.add(f"children of {parent}")
    return moved


def _generations(people, unions, kids) -> dict[str, int]:
    gen = {pid: 0 for pid in people}
    siblings = _sibling_groups(unions, kids)
    for _ in range(len(people) + len(unions) + 2):
        if not _generation_pass(gen, unions, kids, siblings):
            return gen
    involved: set[str] = set()
    for _ in range(len(unions) + 2):
        involved |= _generation_pass(gen, unions, kids, siblings)
    raise LayoutError(
        "could not assign generations: spouses must share a row but their ancestry puts them in different "
        "generations (or the tree has an ancestry cycle); couples involved: " + ", ".join(sorted(involved))
    )


def _couples_and_kids(tree: Tree):
    relations = build_relations(tree)
    unions = {cid: list(couple.partners) for cid, couple in sorted(relations.couples.items())}
    kids = {cid: list(relations.kids.get(cid, [])) for cid in unions}
    return relations, unions, kids


def generation_conflict(tree: Tree) -> str | None:
    """Return a description of why generations cannot be assigned, or None if they can."""
    _, unions, kids = _couples_and_kids(tree)
    try:
        _generations(sorted(tree.people), unions, kids)
    except LayoutError as exc:
        return str(exc)
    return None


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
    relations, unions, kids = _couples_and_kids(tree)
    people = sorted(tree.people)
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

    # Each couple's child connector is a horizontal "bus". Buses of different couples that would overlap
    # are put on different levels so unrelated families never look joined; rows get taller as needed.
    # A child several rows below its parents is reached by a long vertical drop. It must not run behind the boxes
    # in the rows it crosses (it would look as if it came from them), so each drop either enters the child's box
    # off-centre where the way is clear, or detours through the nearest clear column and comes in from above.
    row_boxes: dict[int, list[tuple[float, float]]] = {}
    for pid in people:
        row_boxes.setdefault(gen[pid], []).append((center(pid) - NODE_W / 2, center(pid) + NODE_W / 2))
    routes: dict[tuple[str, str], tuple[float, float | None]] = {}  # (union, child) -> (entry x, detour column)
    for uid in unions:
        parent_row = gen[unions[uid][0]]
        for kid in kids[uid]:
            kx = center(kid)
            blocked = [box for g in range(parent_row + 1, gen[kid]) for box in row_boxes.get(g, [])]
            if not blocked:
                routes[(uid, kid)] = (kx, None)
                continue
            entry = _clear_entry(blocked, kx)
            routes[(uid, kid)] = (entry, None) if entry is not None else (kx, _nearest_free_column(blocked, kx))
    spans: dict[str, tuple[float, float]] = {}
    for uid in unions:
        if kids[uid]:
            xs = [junction_x(uid)] + [routes[(uid, k)][1] if routes[(uid, k)][1] is not None else routes[(uid, k)][0] for k in kids[uid]]
            spans[uid] = (min(xs), max(xs))
    level_of: dict[str, int] = {}
    levels_in_gen: dict[int, int] = {}
    by_gen: dict[int, list[str]] = {}
    for uid in spans:
        by_gen.setdefault(gen[unions[uid][0]], []).append(uid)
    for g, uids in by_gen.items():
        ends: list[float] = []
        for uid in sorted(uids, key=lambda u: (spans[u][0], u)):
            start, end = spans[uid]
            if start == end:  # straight drop: nothing horizontal to collide with
                level_of[uid] = 0
                continue
            for lvl, last in enumerate(ends):
                if start > last + BUS_PAD:
                    level_of[uid] = lvl
                    ends[lvl] = end
                    break
            else:
                level_of[uid] = len(ends)
                ends.append(end)
        levels_in_gen[g] = max(len(ends), 1)
    row_top: dict[int, float] = {}
    cursor = float(MARGIN)
    for g in range(max(gen.values()) + 1):
        row_top[g] = cursor
        cursor += NODE_H + max(ROW_GAP, 2 * BUS_EDGE + levels_in_gen.get(g, 1) * BUS_STEP)

    def row_y(g: int) -> float:
        return row_top[g]

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
        union = {"id": uid, "x": _num(jx), "y": _num(jy), "members": list(members)}
        couple = relations.couples[uid]
        if couple.partnerships:
            union["partnerships"] = [
                {k: v for k, v in dataclasses.asdict(p).items() if v is not None} for p in couple.partnerships
            ]
        if couple.ended:
            union["ended"] = True
        out_unions.append(union)
        if multi:
            for pid in members:
                c = center(pid)
                edge_x = c + NODE_W / 2 if c < jx else c - NODE_W / 2
                edges.append(
                    {"from": pid, "to": uid, "kind": "spouse", "points": [[_num(edge_x), _num(jy)], [_num(jx), _num(jy)]]}
                )
        mid = row_y(g) + NODE_H + BUS_EDGE + level_of.get(uid, 0) * BUS_STEP
        for kid in kids[uid]:
            entry_x, detour = routes[(uid, kid)]
            ky = row_y(gen[kid])
            if detour is None:
                path = [(jx, jy), (jx, mid), (entry_x, mid), (entry_x, ky)]
            else:
                above = ky - JOG_EDGE
                path = [(jx, jy), (jx, mid), (detour, mid), (detour, above), (entry_x, above), (entry_x, ky)]
            edges.append(
                {"from": uid, "to": kid, "kind": "child", "points": [[_num(x), _num(y)] for x, y in path]}
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
