from famsite.model import Event, Partnership
from famsite.places import place_index
from famsite.relations import build_relations


def test_place_index(make_tree):
    tree = make_tree([
        {"id": "a", "given": "A", "birth": Event(date="1900", place="Guelph, Ontario"),
         "partnerships": [Partnership("b", type="marriage", start="1925", place="guelph, ontario ")]},
        {"id": "b", "given": "B", "death": Event(place="Surrey, BC")},
    ])
    assert place_index(tree, build_relations(tree)) == [
        {"place": "Guelph, Ontario", "slug": "guelph-ontario", "entries": [
            {"id": "a", "what": "born", "date": "1900"},
            {"id": "a", "what": "married", "date": "1925"},
            {"id": "b", "what": "married", "date": "1925"}]},
        {"place": "Surrey, BC", "slug": "surrey-bc", "entries": [{"id": "b", "what": "died", "date": None}]},
    ]
