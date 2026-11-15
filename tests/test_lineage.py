from cronicl.site.lineage import ancestor_outline, count_people, descendant_outline
from cronicl.core.model import Event
from cronicl.core.relations import build_relations


def people():
    return [
        {"id": "gg", "given": "GG"},
        {"id": "g", "given": "G", "parents": ["gg"]},
        {"id": "p", "given": "P", "parents": ["g"]},
        {"id": "q", "given": "Q"},
        {"id": "me", "given": "Me", "parents": ["p", "q"]},
        {"id": "k2", "given": "Kay", "birth": Event(date="1990"), "parents": ["me"]},
        {"id": "k1", "given": "Jay", "birth": Event(date="1985"), "parents": ["me"]},
        {"id": "gk", "given": "GK", "parents": ["k1"]},
    ]


def ids(nodes):
    return [{n["id"]: ids(n["children"])} for n in nodes]


def test_ancestor_outline_has_the_same_shape_as_the_descendant_outline(make_tree):
    tree = make_tree(people())
    rel = build_relations(tree)
    assert ids(ancestor_outline(tree, rel, "me")) == [{"p": [{"g": [{"gg": []}]}]}, {"q": []}]
    assert ids(ancestor_outline(tree, rel, "k1")) == [{"me": [{"p": [{"g": [{"gg": []}]}]}, {"q": []}]}]  # no fourth-generation cut
    assert ancestor_outline(tree, rel, "gg") == []
    node = ancestor_outline(tree, rel, "me")[0]
    assert node["name"] == "P" and set(node) == {"id", "name", "years", "children"}
    assert count_people(ancestor_outline(tree, rel, "me")) == 4


def test_descendant_outline_orders_by_birth_and_counts(make_tree):
    tree = make_tree(people())
    rel = build_relations(tree)
    outline = descendant_outline(tree, rel, "me")
    assert [(n["id"], [c["id"] for c in n["children"]]) for n in outline] == [("k1", ["gk"]), ("k2", [])]
    assert count_people(outline) == 3 and descendant_outline(tree, rel, "gk") == []
    assert outline[0]["years"] == "b. 1985" and outline[0]["name"] == "Jay"


def test_lineage_builders_survive_a_cycle(make_tree):
    tree = make_tree([{"id": "x", "given": "X", "parents": ["y"]}, {"id": "y", "given": "Y", "parents": ["x"]}])
    rel = build_relations(tree)
    assert [n["id"] for n in ancestor_outline(tree, rel, "x")] == ["y"] and isinstance(descendant_outline(tree, rel, "x"), list)
