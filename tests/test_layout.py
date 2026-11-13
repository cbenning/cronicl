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
        (x0, y0), (x1, y1) = edge["points"][1:3]  # the bus: the horizontal run under the parents' row
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
    # two siblings, each with a spouse, in one family: their couples sit side by side in one row
    kids_a = [person(f"ka{i}", parents=["a1", "a2"]) for i in range(6)]
    tree = make_tree(
        [person("g1"), person("g2"), person("a1", parents=["g1", "g2"]), person("a2"),
         person("b1", parents=["g1", "g2"]), person("b2"), person("kb", parents=["b1", "b2"])] + kids_a
    )
    layout = compute_layout(tree)
    assert_invariants(tree, layout)  # includes the no-shared-bus-segment check
    buses = {e["from"]: e["points"][1:3] for e in layout["edges"] if e["kind"] == "child"}
    (a0, ya), (a1, _) = buses["a1+a2"]
    (b0, yb), (b1, _) = buses["b1+b2"]
    overlap = min(max(a0, a1), max(b0, b1)) >= max(min(a0, a1), min(b0, b1))
    assert not overlap or ya != yb, "overlapping buses of neighbouring couples must be on different levels"


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


def test_unions_list_their_members_so_the_viewer_can_highlight_a_family(make_tree):
    tree = nuclear(make_tree)
    layout = compute_layout(tree)
    assert layout["unions"][0]["members"] == ["a", "b"]
    solo = compute_layout(make_tree([person("a"), person("c", parents=["a"])]))
    assert solo["unions"][0]["members"] == ["a"]


def test_ended_partnership_is_flagged_on_the_union(make_tree):
    from famsite.model import Partnership

    tree = make_tree(
        [
            person("a", partnerships=[Partnership("b", type="marriage", start="1955", end="1971", end_reason="divorce")]),
            person("b"),
            person("c", spouse=["d"]),
            person("d"),
        ]
    )
    unions = {u["id"]: u for u in compute_layout(tree)["unions"]}
    assert unions["a+b"]["ended"] is True
    assert unions["a+b"]["partnerships"] == [
        {"type": "marriage", "start": "1955", "end": "1971", "end_reason": "divorce"}
    ]
    assert "ended" not in unions["c+d"] and "partnerships" not in unions["c+d"]


def segments_crossing_foreign_boxes(layout):
    """(edge, node) pairs where a vertical or horizontal connector segment passes behind a box it is not attached to."""
    nodes = layout["nodes"]
    hits = []
    for edge in layout["edges"]:
        for (x1, y1), (x2, y2) in zip(edge["points"], edge["points"][1:]):
            for n in nodes:
                if n["id"] in (edge["from"], edge["to"]):
                    continue
                inside_x = min(x1, x2) < n["x"] + n["w"] and max(x1, x2) > n["x"]
                inside_y = min(y1, y2) < n["y"] + n["h"] and max(y1, y2) > n["y"]
                if inside_x and inside_y:
                    hits.append((edge["from"], edge["to"], n["id"]))
    return hits


def long_drop_tree(make_tree):
    """Siblings share a row, so when x marries into a deeper family his whole sibship drops two rows below
    their parents, beneath row 1 (which holds the spouse's side of the family)."""
    people = [person("gp1"), person("gp2")]
    people += [person(f"k{i}", parents=["gp1", "gp2"]) for i in range(3)]
    people += [person("sp1"), person("z", parents=["k0", "sp1"]), person("a"), person("b")]
    people += [person(f"c{i}", parents=["a", "b"]) for i in range(3)]
    people += [person("x", parents=["a", "b"], spouse=["z"])]
    return make_tree(people)


def test_long_drops_never_pass_behind_other_people(make_tree):
    tree = long_drop_tree(make_tree)
    layout = compute_layout(tree)
    gens = {n["id"]: n["y"] for n in layout["nodes"]}
    assert gens["x"] > gens["a"] + 2 * NODE_H, "fixture should put x at least two rows below his parents"
    assert segments_crossing_foreign_boxes(layout) == []
    assert_invariants(tree, layout)


def components_of(layout):
    """Connected groups of people according to the layout's own connectors."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for node in layout["nodes"]:
        find(node["id"])
    for edge in layout["edges"]:
        parent[find(edge["from"])] = find(edge["to"])
    groups = {}
    for node in layout["nodes"]:
        groups.setdefault(find(node["id"]), []).append(node)
    return list(groups.values())


def x_extent(nodes):
    return min(n["x"] for n in nodes), max(n["x"] + n["w"] for n in nodes)


def islands_tree(make_tree):
    """A big family (three generations, five grandchildren), a small family, and three people with no relatives."""
    people = [person("g1"), person("g2")]
    people += [person(f"p{i}", parents=["g1", "g2"]) for i in range(3)]
    people += [person(f"s{i}") for i in range(2)]
    people += [person(f"c{i}", parents=["p0", "s0"]) for i in range(2)]
    people += [person(f"d{i}", parents=["p1", "s1"]) for i in range(3)]
    people += [person("u1"), person("u2"), person("kid", parents=["u1", "u2"])]
    people += [person("loner-b"), person("loner-a"), person("loner-c")]
    return make_tree(people)


def test_unrelated_families_get_their_own_horizontal_bands_largest_first(make_tree):
    tree = islands_tree(make_tree)
    layout = compute_layout(tree)
    assert_invariants(tree, layout)
    groups = [g for g in components_of(layout) if len(g) > 1]
    assert len(groups) == 2
    big, small = sorted(groups, key=len, reverse=True)
    big_lo, big_hi = x_extent(big)
    small_lo, small_hi = x_extent(small)
    assert small_lo >= big_hi + H_GAP, "the small family must not sit among the big family's boxes"
    assert {n["id"] for n in small} == {"u1", "u2", "kid"}
    assert len(big) > len(small)


def test_people_without_relatives_sit_in_a_labelled_grid_below_everything_else(make_tree):
    tree = islands_tree(make_tree)
    layout = compute_layout(tree)
    loners = [n for n in layout["nodes"] if n["id"].startswith("loner")]
    others = [n for n in layout["nodes"] if not n["id"].startswith("loner")]
    assert len(loners) == 3
    assert min(n["y"] for n in loners) >= max(n["y"] + n["h"] for n in others) + 56
    assert [n["id"] for n in sorted(loners, key=lambda n: (n["y"], n["x"]))] == ["loner-a", "loner-b", "loner-c"]
    labels = [l for l in layout["labels"] if l["kind"] == "loners"]
    assert [l["text"] for l in labels] == ["Not connected to anyone"]
    assert labels[0]["y"] < min(n["y"] for n in loners)


def test_a_single_connected_tree_is_laid_out_as_before_and_has_no_labels(make_tree):
    layout = compute_layout(nuclear(make_tree))
    assert "labels" not in layout
    assert len(components_of(layout)) == 1


def test_many_loners_wrap_into_rows_instead_of_one_long_line(make_tree):
    people = [person("a"), person("b"), person("c", parents=["a", "b"])]
    people += [person(f"x{i:02d}") for i in range(30)]
    layout = compute_layout(make_tree(people))
    loner_rows = {n["y"] for n in layout["nodes"] if n["id"].startswith("x")}
    assert len(loner_rows) >= 3
    assert layout["bounds"]["w"] < 12 * (160 + 24) + 200


def test_only_unconnected_people_still_lays_out(make_tree):
    layout = compute_layout(make_tree([person("a"), person("b")]))
    assert len(layout["nodes"]) == 2 and layout["edges"] == []
    assert layout["bounds"]["w"] > 0 and layout["bounds"]["h"] > 0


def test_islands_keep_every_connector_clear_of_foreign_boxes(make_tree):
    layout = compute_layout(islands_tree(make_tree))
    assert segments_crossing_foreign_boxes(layout) == []


def test_each_island_is_labelled_with_its_commonest_surname(make_tree):
    tree = make_tree([
        {"id": "a", "given": "A", "surname": "Smith"},
        {"id": "b", "given": "B", "surname": "Smith", "parents": ["a"]},
        {"id": "c", "given": "C", "surname": "Jones", "parents": ["a"]},
        {"id": "x", "given": "X", "surname": "Lee"},
        {"id": "y", "given": "Y", "surname": "Abel", "parents": ["x"]},
        {"id": "m", "given": "M"},
        {"id": "n", "given": "N", "parents": ["m"]},
        {"id": "z", "given": "Z", "surname": "Solo"},
    ])
    layout = compute_layout(tree)
    assert sorted((l["kind"], l["text"]) for l in layout["labels"]) == [
        ("island", "Abel family · 2"),  # a tie goes to the alphabetically first surname
        ("island", "Family · 2"),  # nobody in the island has a surname
        ("island", "Smith family · 3"),
        ("loners", "Not connected to anyone"),
    ]
    by_id = {n["id"]: n for n in layout["nodes"]}
    smith = next(l for l in layout["labels"] if l["text"].startswith("Smith"))
    xs = [by_id[i]["x"] for i in "abc"]
    assert min(xs) <= smith["x"] <= max(xs) + 160
