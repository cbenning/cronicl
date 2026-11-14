import json
from datetime import date

from cronicl.site.focus import focus_people, focus_tree, hidden_counts
from cronicl.site.layout import compute_layout
from cronicl.core.model import Event
from cronicl.core.relations import build_relations
from cronicl.site.render import build_site

TODAY = date(2026, 10, 10)


def person(pid, **kw):
    return {"id": pid, "given": pid, **kw}


def family(make_tree):
    return make_tree(
        [
            person("gp1"), person("gp2"),
            person("p1", parents=["gp1", "gp2"]),
            person("uncle", parents=["gp1", "gp2"]),
            person("p2"),
            person("stepmom", spouse=["p1"]),
            person("f", parents=["p1", "p2"]),
            person("sib", parents=["p1", "p2"]),
            person("sp"),
            person("spp1"), person("spp2"),
            person("spouse-of-f", parents=["spp1", "spp2"]),
            person("c1", parents=["f", "spouse-of-f"]),
            person("c2", parents=["f", "spouse-of-f"]),
            person("csp"),
            person("gc", parents=["c1", "csp"]),
        ]
    )


def test_focus_people_are_the_line_above_and_below_plus_spouses(make_tree):
    tree = family(make_tree)
    got = focus_people(tree, build_relations(tree), "f")
    assert got == {
        "gp1", "gp2", "p1", "p2",            # ancestors
        "f",                                  # the focus
        "spouse-of-f", "c1", "c2", "csp", "gc",  # spouse, descendants, descendants' spouses
    }


def test_siblings_extended_family_and_step_relations_are_left_out(make_tree):
    tree = family(make_tree)
    got = focus_people(tree, build_relations(tree), "f")
    for excluded in ("sib", "uncle", "stepmom", "spp1", "spp2"):
        assert excluded not in got


def test_a_descendants_view_starts_below_and_keeps_only_their_own_line(make_tree):
    tree = family(make_tree)
    got = focus_people(tree, build_relations(tree), "c1")
    assert got == {"gp1", "gp2", "p1", "p2", "f", "spouse-of-f", "spp1", "spp2", "c1", "csp", "gc"}
    assert "c2" not in got and "sib" not in got


def test_focus_tree_lays_out_only_those_people(make_tree):
    tree = family(make_tree)
    relations = build_relations(tree)
    sub = focus_tree(tree, relations, "f")
    layout = compute_layout(sub)
    assert {n["id"] for n in layout["nodes"]} == focus_people(tree, relations, "f")
    ys = {n["id"]: n["y"] for n in layout["nodes"]}
    assert ys["p1"] < ys["f"] < ys["c1"] < ys["gc"]
    assert ys["f"] == ys["spouse-of-f"]


def test_a_person_with_no_relatives_is_alone(make_tree):
    tree = make_tree([person("solo"), person("other")])
    assert focus_people(tree, build_relations(tree), "solo") == {"solo"}


def test_build_writes_a_focus_layout_per_person(tmp_path, make_tree):
    tree = family(make_tree)
    tree.site = {}
    build_site(tree, tmp_path, today=TODAY)
    data = json.loads((tmp_path / "focus" / "f.json").read_text(encoding="utf-8"))
    assert data["focus"] == "f"
    assert {n["id"] for n in data["nodes"]} == focus_people(tree, build_relations(tree), "f")
    assert (tmp_path / "focus" / "sib.json").exists()


def test_focus_files_use_redacted_ids_and_leak_nothing(tmp_path, make_tree):
    tree = make_tree(
        [
            {"id": "old-x", "given": "X", "surname": "Old", "birth": Event(date="1900"), "death": Event(date="1970")},
            {"id": "secret-y", "given": "Y", "surname": "Secret", "birth": Event(date="2000"), "parents": ["old-x"]},
        ]
    )
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    names = sorted(p.name for p in (tmp_path / "focus").iterdir())
    assert "secret-y.json" not in names and any(n.startswith("living-") for n in names)
    for f in (tmp_path / "focus").iterdir():
        text = f.read_text(encoding="utf-8")
        assert "secret" not in text.lower()


def test_rebuild_removes_stale_focus_files(tmp_path, make_tree):
    tree = make_tree([person("a"), person("b")])
    tree.site = {}
    build_site(tree, tmp_path, today=TODAY)
    assert (tmp_path / "focus" / "b.json").exists()
    build_site(make_tree([person("a")]), tmp_path, today=TODAY)
    assert not (tmp_path / "focus" / "b.json").exists()


def test_focus_layout_keeps_the_ended_flag_of_the_parents(make_tree):
    from cronicl.core.model import Partnership

    tree = make_tree(
        [
            person("mum", partnerships=[Partnership("dad", type="marriage", start="1960", end="1975")]),
            person("dad"),
            person("kid", parents=["mum", "dad"]),
        ]
    )
    rel = build_relations(tree)
    layout = compute_layout(focus_tree(tree, rel, "kid"))
    unions = {u["id"]: u for u in layout["unions"]}
    assert unions["dad+mum"]["ended"] is True


def test_hidden_counts_say_how_many_relatives_a_focused_tree_leaves_out(make_tree):
    tree = make_tree([
        {"id": "g", "given": "G"},
        {"id": "p", "given": "P", "parents": ["g"]},
        {"id": "u", "given": "U", "parents": ["g"]},
        {"id": "me", "given": "Me", "parents": ["p"]},
    ])
    rel = build_relations(tree)
    keep = focus_people(tree, rel, "me")
    assert keep == {"g", "p", "me"}
    assert hidden_counts(rel, keep) == {"g": 1, "p": 1}  # g's child u; p's sibling u
