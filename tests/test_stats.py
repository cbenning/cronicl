from famsite.model import Event
from famsite.relations import build_relations
from famsite.stats import site_stats
from famsite.timeline import build_timeline


def test_site_stats(make_tree):
    tree = make_tree([
        {"id": "g", "given": "G", "surname": "Müller", "birth": Event(date="1850")},
        {"id": "p", "given": "P", "surname": "MULLER", "parents": ["g"]},
        {"id": "c", "given": "C", "surname": "Smith", "parents": ["p"], "death": Event(date="2001-05")},
        {"id": "x", "given": "X"},
    ])
    rel = build_relations(tree)
    stats = site_stats(tree, rel, build_timeline(tree, rel))
    assert stats == {
        "people": 4, "generations": 3, "first_year": 1850, "last_year": 2001,
        "surnames": [
            {"surname": "Müller", "slug": "muller", "count": 2},
            {"surname": "Smith", "slug": "smith", "count": 1},
        ],
    }


def test_site_stats_of_nothing(make_tree):
    tree = make_tree([])
    rel = build_relations(tree)
    assert site_stats(tree, rel, build_timeline(tree, rel)) == {
        "people": 0, "generations": 0, "first_year": None, "last_year": None, "surnames": []}
