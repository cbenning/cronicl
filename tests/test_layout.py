import pytest

from famsite.layout import H_GAP, NODE_H, NODE_W, LayoutError, compute_layout
from famsite.relations import build_relations


def person(pid, **kw):
    return {"id": pid, "given": pid, **kw}


def assert_invariants(tree, layout):
    nodes = {n["id"]: n for n in layout["nodes"]}
    assert set(nodes) == set(tree.people)
    rows: dict[float, list[dict]] = {}
    for node in nodes.values():
        rows.setdefault(node["y"], []).append(node)
    for row in rows.values():
        row.sort(key=lambda n: n["x"])
        for left, right in zip(row, row[1:]):
            assert right["x"] >= left["x"] + left["w"] + H_GAP - 1e-9, "nodes overlap or crowd"
    rel = build_relations(tree)
    for child, cid in rel.birth_couple.items():
        for partner in rel.couples[cid].partners:
            assert nodes[child]["y"] >= nodes[partner]["y"] + NODE_H, "child must be below parents"
    known = set(nodes) | {u["id"] for u in layout["unions"]}
    for edge in layout["edges"]:
        assert edge["from"] in known and edge["to"] in known
        assert len(edge["points"]) >= 2
    assert layout["bounds"]["w"] > 0 and layout["bounds"]["h"] > 0
    assert_buses_do_not_overlap(layout)


def assert_buses_do_not_overlap(layout):
    """Child connectors of different couples must never share a horizontal line segment."""
    buses = []
    for edge in layout["edges"]:
        if edge["kind"] != "child":
            continue
        (_, _), (x0, y0), (x1, y1), (_, _) = edge["points"]
        assert y0 == y1
        buses.append((y0, min(x0, x1), max(x0, x1), edge["from"]))
    for i, (ya, a0, a1, ca) in enumerate(buses):
        for yb, b0, b1, cb in buses[i + 1:]:
            if ca != cb and ya == yb and a0 <= b1 and b0 <= a1 and not (a0 == a1 or b0 == b1):
                raise AssertionError(f"couples {ca} and {cb} share a bus segment at y={ya}: {a0}-{a1} / {b0}-{b1}")


def nuclear(make_tree):
    return make_tree(
        [
            person("a"),
            person("b"),
            person("c", parents=["a", "b"]),
            person("d", parents=["a", "b"]),
            person("e", parents=["a", "b"]),
        ]
    )


def test_nuclear_family(make_tree):
    tree = nuclear(make_tree)
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    nodes = {n["id"]: n for n in layout["nodes"]}
    assert nodes["a"]["y"] == nodes["b"]["y"]
    assert nodes["c"]["y"] > nodes["a"]["y"]
    assert nodes["b"]["x"] - nodes["a"]["x"] == NODE_W + H_GAP
    kinds = sorted(e["kind"] for e in layout["edges"])
    assert kinds == ["child", "child", "child", "spouse", "spouse"]
    assert [u["id"] for u in layout["unions"]] == ["a+b"]


def test_two_marriages_share_a_row(make_tree):
    tree = make_tree(
        [
            person("x"),
            person("a"),
            person("b"),
            person("k1", parents=["x", "a"]),
            person("k2", parents=["x", "b"]),
        ]
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    nodes = {n["id"]: n for n in layout["nodes"]}
    assert nodes["x"]["y"] == nodes["a"]["y"] == nodes["b"]["y"]


def test_single_parent_has_no_spouse_edge(make_tree):
    tree = make_tree([person("a"), person("c", parents=["a"])])
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    assert [e["kind"] for e in layout["edges"]] == ["child"]


def test_pedigree_collapse_draws_each_person_once(make_tree):
    tree = make_tree(
        [
            person("A"), person("B"),
            person("C", parents=["A", "B"]), person("D", parents=["A", "B"]),
            person("Z"), person("Y"),
            person("E", parents=["C", "Z"]), person("F", parents=["D", "Y"]),
            person("G", parents=["E", "F"]),
        ]
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    assert len([n for n in layout["nodes"] if n["id"] == "G"]) == 1


def test_disconnected_families_do_not_overlap(make_tree):
    tree = make_tree(
        [
            person("a1", spouse=["a2"]), person("a2"),
            person("b1", spouse=["b2"]), person("b2"),
            person("lone"),
        ]
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)


def test_layout_is_deterministic_and_order_independent(make_tree):
    a = compute_layout(nuclear(make_tree))
    b = compute_layout(nuclear(make_tree))
    assert a == b
    reordered = make_tree(
        [
            person("e", parents=["b", "a"]),
            person("d", parents=["a", "b"]),
            person("c", parents=["a", "b"]),
            person("b"),
            person("a"),
        ]
    )
    assert compute_layout(reordered) == a


def test_empty_tree(make_tree):
    layout = compute_layout(make_tree([]))
    assert layout["nodes"] == [] and layout["edges"] == []
    assert layout["version"] == 1


def test_cycle_raises_instead_of_hanging(make_tree):
    # Review focus 5.
    tree = make_tree([person("a", parents=["b"]), person("b", parents=["a"])])
    with pytest.raises(LayoutError):
        compute_layout(tree)


def test_self_parent_raises(make_tree):
    with pytest.raises(LayoutError):
        compute_layout(make_tree([person("a", parents=["a"])]))


def test_dangling_references_are_ignored(make_tree):
    tree = make_tree([person("a", parents=["ghost"], spouse=["phantom"])])
    layout = compute_layout(tree)
    assert [n["id"] for n in layout["nodes"]] == ["a"]


def test_siblings_share_a_row_even_when_one_marries_into_a_deeper_branch(make_tree):
    # a+b have s1 and s2. s1 marries x, whose own line is two generations deeper than a+b.
    tree = make_tree(
        [
            person("a"), person("b"),
            person("s1", parents=["a", "b"]), person("s2", parents=["a", "b"]),
            person("r"), person("r2"),
            person("q", parents=["r", "r2"]), person("q2"),
            person("x", parents=["q", "q2"]),
            person("kid", parents=["s1", "x"]),
        ]
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    rows = {n["id"]: n["y"] for n in layout["nodes"]}
    assert rows["s1"] == rows["s2"]
    assert rows["s1"] > rows["a"]


def test_half_siblings_share_a_row_too(make_tree):
    # p has c1 with b and c2 with d; c1 marries into a deeper branch, c2 must follow.
    tree = make_tree(
        [
            person("p"), person("b"), person("d"),
            person("c1", parents=["p", "b"]), person("c2", parents=["p", "d"]),
            person("r"), person("r2"),
            person("q", parents=["r", "r2"]), person("q2"),
            person("x", parents=["q", "q2"]),
            person("kid", parents=["c1", "x"]),
        ]
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    rows = {n["id"]: n["y"] for n in layout["nodes"]}
    assert rows["c1"] == rows["c2"]


def test_node_height_leaves_room_for_two_name_lines_and_years():
    assert NODE_H >= 64


def test_neighbouring_couples_with_many_children_get_separate_buses(make_tree):
    kids_a = [person(f"ka{i}", parents=["a1", "a2"]) for i in range(6)]
    tree = make_tree(
        [person("a1"), person("a2"), person("b1"), person("b2"), person("kb", parents=["b1", "b2"])] + kids_a
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)  # includes the no-shared-bus-segment check
    buses = {e["from"]: e["points"][1][1] for e in layout["edges"] if e["kind"] == "child"}
    assert buses["a1+a2"] != buses["b1+b2"]


def test_row_gap_grows_when_a_generation_needs_many_buses(make_tree):
    # many adjacent couples whose child buses all overlap force several bus levels
    people = []
    for n in range(8):
        people += [person(f"p{n}a"), person(f"p{n}b")]
        people += [person(f"k{n}{i}", parents=[f"p{n}a", f"p{n}b"]) for i in range(3)]
    tree = make_tree(people)
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    nodes = {n["id"]: n for n in layout["nodes"]}
    # children never overlap the buses drawn above them
    assert nodes["k00"]["y"] > nodes["p0a"]["y"] + NODE_H
