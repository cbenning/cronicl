import json
from datetime import date

from famsite.model import Event, Partnership
from famsite.relations import build_relations
from famsite.render import build_site
from famsite.timeline import build_timeline

TODAY = date(2026, 10, 10)


def p(pid, given, surname, **kw):
    return {"id": pid, "given": given, "surname": surname, **kw}


def sample(make_tree):
    return make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920-05-01", place="Halifax, NS"),
              death=Event(date="1990")),
            p("brown-mary", "Mary", "Brown", birth=Event(date="~1925"), death=Event(date="2001-02-03"),
              partnerships=[Partnership("smith-john", type="marriage", start="1948-06-20", place="Halifax, NS")]),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950", place="Vancouver, BC"),
              parents=["smith-john", "brown-mary"]),
            p("nodates", "No", "Dates"),
            p("weird", "We", "Ird", birth=Event(date="BET 1900 AND 1910")),
        ]
    )


def timeline(tree):
    return build_timeline(tree, build_relations(tree))


def test_events_are_dated_typed_and_sorted(make_tree):
    t = timeline(sample(make_tree))
    assert [(e["year"], e["type"]) for e in t["events"]] == [
        (1920, "birth"),
        (1925, "birth"),
        (1948, "marriage"),
        (1950, "birth"),
        (1990, "death"),
        (2001, "death"),
    ]
    assert t["range"] == {"min": 1920, "max": 2001}


def test_event_details(make_tree):
    t = timeline(sample(make_tree))
    by_id = {e["id"]: e for e in t["events"]}
    birth = by_id["birth:smith-john"]
    assert birth["date"] == "1920-05-01" and birth["place"] == "Halifax, NS" and birth["people"] == ["smith-john"]
    assert birth["approx"] is False
    assert by_id["birth:brown-mary"]["approx"] is True
    marriage = by_id["marriage:brown-mary+smith-john"]
    assert marriage["people"] == ["brown-mary", "smith-john"]
    assert marriage["place"] == "Halifax, NS" and marriage["date"] == "1948-06-20"


def test_people_without_any_dated_event_are_listed_as_undated(make_tree):
    t = timeline(sample(make_tree))
    assert t["undated"] == ["nodates", "weird"]


def test_relationships_are_included_for_person_timelines(make_tree):
    t = timeline(sample(make_tree))
    bob = t["people"]["smith-bob"]
    assert bob["name"] == "Bob Smith"
    assert bob["parents"] == ["smith-john", "brown-mary"]
    john = t["people"]["smith-john"]
    assert john["children"] == ["smith-bob"] and john["spouses"] == ["brown-mary"]
    assert t["people"]["smith-bob"]["siblings"] == []


def test_siblings_are_derived_from_shared_parents(make_tree):
    tree = make_tree(
        [
            p("a", "A", "X"),
            p("b", "B", "X"),
            p("c1", "C", "One", parents=["a", "b"]),
            p("c2", "C", "Two", parents=["a", "b"]),
        ]
    )
    assert timeline(tree)["people"]["c1"]["siblings"] == ["c2"]


def test_empty_tree_has_null_range(make_tree):
    t = timeline(make_tree([]))
    assert t["events"] == [] and t["range"] == {"min": None, "max": None}


def test_build_writes_timeline_json_and_respects_redaction(tmp_path, make_tree):
    tree = make_tree(
        [
            p("old-x", "X", "Old", birth=Event(date="1900"), death=Event(date="1970")),
            p("young-y", "Y", "Young", birth=Event(date="2012-04-05", place="Secrettown")),
        ]
    )
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    text = (tmp_path / "timeline.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert [e["year"] for e in data["events"]] == [1900, 1970]
    assert "2012" not in text and "Secrettown" not in text and "Young" not in text and "young-y" not in text
