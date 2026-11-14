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


from famsite.places import group_places


def _p(name):
    return {"place": name, "slug": name.lower().replace(", ", "-").replace(" ", "-"), "entries": []}


def test_places_group_by_the_last_part_of_the_name():
    places = [_p(n) for n in [
        "Germany", "Hamburg, Germany", "Hampton General Hospital", "Guelph, Ontario",
        "Nurtingen, Swabia, Baden-Wurttemberg, Germany", "Ontario, Canada", "Sooke, , British Columbia, Canada"]]
    groups = group_places(places)
    assert [(g["name"], [p["place"] for p in g["places"]]) for g in groups] == [
        ("Canada", ["Ontario, Canada", "Sooke, , British Columbia, Canada"]),
        ("Germany", ["Germany", "Hamburg, Germany", "Nurtingen, Swabia, Baden-Wurttemberg, Germany"]),
        ("Ontario", ["Guelph, Ontario"]),
        ("Other places", ["Hampton General Hospital"]),
    ]
    assert [g["slug"] for g in groups] == ["canada", "germany", "ontario", "other"]


def test_site_yml_can_fold_a_region_into_its_country():
    places = [_p("Guelph, Ontario"), _p("Ontario, Canada"), _p("Utrecht, Holland"), _p("Amsterdam, Netherlands")]
    groups = group_places(places, {"ontario": "Canada", "Holland": "Netherlands"})
    assert [(g["name"], len(g["places"])) for g in groups] == [("Canada", 2), ("Netherlands", 2)]
