from cronicl.home import home_person
from cronicl.model import Event
from cronicl.relations import build_relations


def people():
    return [
        {"id": "g", "given": "G", "birth": Event(date="1900")},
        {"id": "h", "given": "H", "birth": Event(date="1890")},
        {"id": "p", "given": "P", "parents": ["g", "h"]},
        {"id": "c", "given": "C", "parents": ["p"]},
        {"id": "z", "given": "Z"},
    ]


def test_configured_home_wins(make_tree):
    tree = make_tree(people())
    tree.site = {"home": "c"}
    assert home_person(tree, build_relations(tree)) == "c"


def test_default_is_most_descendants_then_earliest_birth_then_id(make_tree):
    tree = make_tree(people())
    assert home_person(tree, build_relations(tree)) == "h"  # g and h both have 2; h was born first


def test_unknown_home_falls_back_and_empty_tree_has_none(make_tree):
    tree = make_tree(people())
    tree.site = {"home": "nobody"}
    assert home_person(tree, build_relations(tree)) == "h"
    empty = make_tree([])
    assert home_person(empty, build_relations(empty)) is None
