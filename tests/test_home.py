from cronicl.site.home import home_person
from cronicl.core.model import Event
from cronicl.core.relations import build_relations


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


def test_without_a_configured_home_nobody_is_the_home_person(make_tree):
    tree = make_tree(people())
    assert home_person(tree, build_relations(tree)) is None
    tree.site = {"home": "nobody"}
    assert home_person(tree, build_relations(tree)) is None  # an unknown id is no one either


def test_an_empty_tree_has_no_home_person(make_tree):
    empty = make_tree([])
    assert home_person(empty, build_relations(empty)) is None
