from famsite.lineage import ancestor_tree, count_descendants, descendant_outline
from famsite.model import Event
from famsite.relations import build_relations


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


def ids(node):
    return {node["id"]: [ids(x) for x in node["parents"]]}


def test_ancestor_tree_is_four_generations_and_draws_only_what_is_recorded(make_tree):
    tree = make_tree(people())
    rel = build_relations(tree)
    assert ids(ancestor_tree(tree, rel, "me")) == {"me": [{"p": [{"g": [{"gg": []}]}]}, {"q": []}]}
    assert ids(ancestor_tree(tree, rel, "k1")) == {"k1": [{"me": [{"p": [{"g": []}]}, {"q": []}]}]}  # gg is a fifth generation
    assert ancestor_tree(tree, rel, "gg") is None


def test_descendant_outline_orders_by_birth_and_counts(make_tree):
    tree = make_tree(people())
    rel = build_relations(tree)
    outline = descendant_outline(tree, rel, "me")
    assert [(n["id"], [c["id"] for c in n["children"]]) for n in outline] == [("k1", ["gk"]), ("k2", [])]
    assert count_descendants(outline) == 3 and descendant_outline(tree, rel, "gk") == []
    assert outline[0]["years"] == "b. 1985" and outline[0]["name"] == "Jay"


def test_lineage_builders_survive_a_cycle(make_tree):
    tree = make_tree([{"id": "x", "given": "X", "parents": ["y"]}, {"id": "y", "given": "Y", "parents": ["x"]}])
    rel = build_relations(tree)
    assert ancestor_tree(tree, rel, "x")["id"] == "x" and isinstance(descendant_outline(tree, rel, "x"), list)
