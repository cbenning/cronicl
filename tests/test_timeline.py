import json
from datetime import date

from cronicl.core.model import Event, LifeEvent, Partnership
from cronicl.core.relations import build_relations
from cronicl.site.render import build_site
from cronicl.site.timeline import build_timeline

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


def test_partnership_start_and_end_become_events(make_tree):
    tree = make_tree(
        [
            p("a", "A", "X", partnerships=[
                Partnership("b", type="marriage", start="1950-06-01", end="1960", end_reason="divorce", place="Reno")
            ]),
            p("b", "B", "Y"),
        ]
    )
    events = build_timeline(tree, build_relations(tree))["events"]
    by_id = {e["id"]: e for e in events}
    assert by_id["marriage:a+b"]["year"] == 1950 and by_id["marriage:a+b"]["kind"] == "marriage"
    end = by_id["divorce:a+b"]
    assert (end["year"], end["reason"], end["kind"], end["people"], end["place"]) == (
        1960, "divorce", "marriage", ["a", "b"], "",
    )


def test_non_marriage_start_is_a_partnership_event_and_unknown_end_has_no_event(make_tree):
    tree = make_tree(
        [
            p("a", "A", "X", partnerships=[Partnership("b", type="engagement", start="1949", end="unknown")]),
            p("b", "B", "Y"),
        ]
    )
    ids = [e["id"] for e in build_timeline(tree, build_relations(tree))["events"]]
    assert ids == ["partnership:a+b"]


def test_later_partnerships_get_numbered_ids_and_same_year_end_sorts_before_death(make_tree):
    tree = make_tree(
        [
            p("a", "A", "X", death=Event(date="1960"), partnerships=[
                Partnership("b", type="marriage", start="1950", end="1960", end_reason="divorce"),
                Partnership("b", type="marriage", start="1970"),
            ]),
            p("b", "B", "Y"),
        ]
    )
    ids = [e["id"] for e in build_timeline(tree, build_relations(tree))["events"]]
    assert ids == ["marriage:a+b", "divorce:a+b", "death:a", "marriage:a+b:1"]


from cronicl.site.timeline import event_text  # noqa: E402

NAMES = {"a": "Ann", "b": "Bo", "p": "Pat", "q": "Quinn", "s": "Sam", "x": "Xi"}


def ev(etype, people, **kw):
    return {"id": f"{etype}:{'+'.join(people)}", "type": etype, "people": people, **kw}


def test_event_text_for_births_deaths_and_marriages():
    born = ev("birth", ["a"])
    assert event_text(born, NAMES, "a") == "born"
    assert event_text(born, NAMES, None) == "Ann born"
    assert event_text(ev("death", ["s"]), NAMES, "a") == "Sam died"
    marriage = ev("marriage", ["a", "b"], kind="marriage")
    assert event_text(marriage, NAMES, "a") == "married Bo"
    assert event_text(marriage, NAMES, None) == "Ann & Bo married"


def test_event_text_for_partnership_starts():
    engaged = ev("partnership", ["p", "q"], kind="engagement")
    assert event_text(engaged, NAMES, "p") == "engaged to Quinn"
    assert event_text(engaged, NAMES, None) == "Pat & Quinn engaged"
    assert event_text(ev("partnership", ["p", "q"], kind="civil-union"), NAMES, "p") == "entered a civil union with Quinn"
    assert event_text(ev("partnership", ["p", "q"], kind="unknown"), NAMES, None) == "Pat & Quinn became partners"


def test_event_text_for_partnership_ends():
    divorce = ev("divorce", ["a", "b"], kind="marriage", reason="divorce")
    assert event_text(divorce, NAMES, "a") == "divorced Bo"
    assert event_text(divorce, NAMES, None) == "Ann & Bo divorced"
    annulled = {**divorce, "reason": "annulment"}
    assert event_text(annulled, NAMES, "a") == "marriage to Bo annulled"
    assert event_text(annulled, NAMES, None) == "Marriage of Ann & Bo annulled"
    ended = {**divorce, "reason": ""}
    assert event_text(ended, NAMES, None) == "Marriage of Ann & Bo ended"
    assert event_text(ended, NAMES, "a") == "marriage to Bo ended"
    split = {**divorce, "kind": "partnership", "reason": "separation"}
    assert event_text(split, NAMES, "a") == "separated from Bo"
    assert event_text({**divorce, "kind": "partnership", "reason": ""}, NAMES, "a") == "partnership with Bo ended"


def life(make_tree):
    return make_tree(
        [
            p("par", "Par", "Ent", birth=Event(date="1890"), death=Event(date="1970")),
            p("me", "Me", "Self", birth=Event(date="1920-05-01"), death=Event(date="1990"), parents=["par"],
              partnerships=[Partnership("sp", type="marriage", start="1948-06-20", end="1960", end_reason="divorce")]),
            p("sp", "Sp", "Ouse", birth=Event(date="1925"), death=Event(date="1995")),
            p("sib", "Sib", "Ling", birth=Event(date="1922"), death=Event(date="1950"), parents=["par"]),
            p("kid", "Kid", "Self", birth=Event(date="1950-04-30"), parents=["me", "sp"]),
            p("stranger", "Str", "Anger", birth=Event(date="1960")),
        ]
    )


def test_person_events_apply_the_role_rules_and_wording(make_tree):
    tree = life(make_tree)
    data = build_timeline(tree, build_relations(tree))
    rows = [(r["id"], r["role"], r["text"]) for r in data["people"]["me"]["events"]]
    assert rows == [
        ("birth:me", "self", "born"),
        ("birth:sib", "sibling", "Sib Ling born"),
        ("marriage:me+sp", "self", "married Sp Ouse"),
        ("death:sib", "sibling", "Sib Ling died"),
        ("birth:kid", "child", "Kid Self born"),
        ("divorce:me+sp", "self", "divorced Sp Ouse"),
        ("death:par", "parent", "Par Ent died"),
        ("death:me", "self", "died"),
    ]
    assert not any(r["id"] == "birth:stranger" for r in data["people"]["me"]["events"])


def test_person_event_ages_are_exact_and_only_on_own_non_birth_events(make_tree):
    tree = life(make_tree)
    rows = {r["id"]: r for r in build_timeline(tree, build_relations(tree))["people"]["me"]["events"]}
    assert rows["birth:me"]["age"] is None
    assert rows["marriage:me+sp"]["age"] == 28
    assert rows["death:me"]["age"] == 70  # death has only a year: the finest shared precision is the year
    assert rows["death:par"]["age"] is None
    assert rows["divorce:me+sp"]["age"] == 40


def test_age_is_flagged_approximate_and_null_before_birth(make_tree):
    tree = make_tree(
        [
            p("a", "A", "X", birth=Event(date="~1900"), death=Event(date="1950")),
            p("b", "B", "Y", birth=Event(date="1950"),
              partnerships=[Partnership("c", type="marriage", start="1940")]),
            p("c", "C", "Z"),
        ]
    )
    data = build_timeline(tree, build_relations(tree))
    death = next(r for r in data["people"]["a"]["events"] if r["id"] == "death:a")
    assert (death["age"], death["age_approx"]) == (50, True)
    before = next(r for r in data["people"]["b"]["events"] if r["id"] == "marriage:b+c")
    assert before["age"] is None


def test_family_events_carry_text(make_tree):
    tree = life(make_tree)
    by_id = {e["id"]: e for e in build_timeline(tree, build_relations(tree))["events"]}
    assert by_id["marriage:me+sp"]["text"] == "Me Self & Sp Ouse married"
    assert by_id["death:par"]["text"] == "Par Ent died"


def test_person_event_roles_for_partnerships_of_relatives(make_tree):
    tree = make_tree(
        [
            p("grand", "Gran", "D"),
            p("dad", "Dad", "D", parents=["grand"]),
            p("mum", "Mum", "D", partnerships=[
                Partnership("dad", type="marriage", start="1948", end="1960", end_reason="divorce")
            ]),
            p("me", "Me", "D", parents=["dad", "mum"], birth=Event(date="1950"),
              partnerships=[Partnership("wife", type="marriage", start="1975", end="1985", end_reason="divorce")]),
            p("wife", "Wi", "Fe"),
            p("sib", "Sib", "D", parents=["dad", "mum"], birth=Event(date="1952"),
              partnerships=[Partnership("sibwife", type="marriage", start="1978")]),
            p("sibwife", "Sw", "Ife"),
            p("kid", "Kid", "D", parents=["me", "wife"], birth=Event(date="1980"),
              partnerships=[Partnership("kidwife", type="marriage", start="2005", end="2010", end_reason="divorce")]),
            p("kidwife", "Kw", "Ife"),
        ]
    )
    rows = {(r["id"], r["role"]) for r in build_timeline(tree, build_relations(tree))["people"]["me"]["events"]}
    assert ("marriage:dad+mum", "parent") not in rows      # a parent's wedding is not about this person
    assert ("divorce:dad+mum", "parent") not in rows       # nor is a parent's divorce
    assert ("death:dad", "parent") not in rows             # (dad has no death date in this fixture)
    assert ("marriage:me+wife", "self") in rows and ("divorce:me+wife", "self") in rows
    assert ("marriage:sib+sibwife", "sibling") not in rows  # a sibling's marriage is not
    assert ("marriage:kid+kidwife", "child") in rows        # every event of a child is
    assert ("divorce:kid+kidwife", "child") in rows


def test_a_parents_death_stays_on_the_persons_timeline(make_tree):
    tree = make_tree(
        [
            p("dad", "Dad", "D", birth=Event(date="1920"), death=Event(date="1990")),
            p("mum", "Mum", "D", partnerships=[Partnership("dad", type="marriage", start="1948")]),
            p("me", "Me", "D", parents=["dad", "mum"], birth=Event(date="1950")),
        ]
    )
    rows = {(r["id"], r["role"]) for r in build_timeline(tree, build_relations(tree))["people"]["me"]["events"]}
    assert ("death:dad", "parent") in rows
    assert ("marriage:dad+mum", "parent") not in rows


def test_relatives_events_outside_own_lifetime_are_left_out(make_tree):
    tree = make_tree([
        {"id": "mum", "given": "Mum", "birth": Event(date="1910"), "death": Event(date="1950")},
        {"id": "old", "given": "Old", "birth": Event(date="1936"), "death": Event(date="2017"), "parents": ["mum"]},
        {"id": "me", "given": "Me", "birth": Event(date="1938"), "death": Event(date="2016"), "parents": ["mum"]},
        {"id": "twin", "given": "Twin", "birth": Event(date="1938-03"), "parents": ["mum"]},
        {"id": "kid", "given": "Kid", "birth": Event(date="1960"), "parents": ["me"]},
    ])
    rows = build_timeline(tree, build_relations(tree))["people"]["me"]["events"]
    assert [r["id"] for r in rows] == ["birth:me", "birth:twin", "death:mum", "birth:kid", "death:me"]


def test_lifetime_bound_uses_only_the_known_side(make_tree):
    tree = make_tree([
        {"id": "mum", "given": "Mum"},
        {"id": "me", "given": "Me", "death": Event(date="1950"), "parents": ["mum"]},
        {"id": "sib", "given": "Sib", "birth": Event(date="1900"), "death": Event(date="1960"), "parents": ["mum"]},
    ])
    rows = build_timeline(tree, build_relations(tree))["people"]["me"]["events"]
    assert [r["id"] for r in rows] == ["birth:sib", "death:me"]


def test_spans_and_rows(make_tree):
    tree = make_tree([
        {"id": "a", "given": "Ann", "birth": Event(date="1900-07-01"), "death": Event(date="1980")},
        {"id": "b", "given": "Bob", "birth": Event(date="1990")},
        {"id": "c", "given": "Cy", "birth": Event(date="1850")},
        {"id": "d", "given": "Di", "death": Event(date="1970")},
        {"id": "e", "given": "Ed"},
        {"id": "f", "given": "Flo", "birth": Event(date="1995"), "living": False},
    ])
    tl = build_timeline(tree, build_relations(tree), living={"b", "e"})
    spans = {pid: info["span"] for pid, info in tl["people"].items()}
    assert spans == {
        "a": {"start": 1900.5, "end": 1980.5, "open": None},
        "b": {"start": 1990.5, "end": None, "open": "living"},
        "c": {"start": 1850.5, "end": None, "open": "unknown"},
        "d": {"start": None, "end": 1970.5, "open": None},
        "e": {"start": None, "end": None, "open": None},
        "f": {"start": 1995.5, "end": None, "open": "unknown"},
    }
    assert tl["rows"] == ["c", "a", "b", "f", "d"]


def test_build_site_treats_living_by_the_privacy_rule(tmp_path, make_tree):
    tree = make_tree([
        {"id": "b", "given": "Bob", "birth": Event(date="1990")},
        {"id": "f", "given": "Flo", "birth": Event(date="1995"), "living": False},
    ])
    build_site(tree, tmp_path, today=date(2026, 10, 10))
    people = json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))["people"]
    assert people["b"]["span"]["open"] == "living" and people["f"]["span"]["open"] == "unknown"


def test_facts_join_a_persons_own_events_only(make_tree):
    tree = make_tree([
        {"id": "mum", "given": "Mum", "events": [LifeEvent(type="occupation", value="Nurse", date="1930")]},
        {"id": "me", "given": "Me", "birth": Event(date="1920"), "death": Event(date="1990"), "parents": ["mum"],
         "events": [LifeEvent(type="immigration", date="1952-04", place="Halifax"),
                    LifeEvent(type="residence", start="1960", end="1975", place="Surrey"),
                    LifeEvent(type="burial", date="1991"), LifeEvent(type="moved-house", date="1940"),
                    LifeEvent(type="occupation", value="Carpenter")]},
    ])
    tl = build_timeline(tree, build_relations(tree))
    assert [(r["id"], r["text"]) for r in tl["people"]["me"]["events"]] == [
        ("birth:me", "born"), ("fact:me:3", "moved house"), ("fact:me:0", "immigrated"),
        ("fact:me:1", "lived"), ("death:me", "died"), ("fact:me:2", "buried")]
    family = {e["id"]: e for e in tl["events"]}
    assert family["fact:me:0"]["text"] == "Me immigrated" and family["fact:mum:0"]["text"] == "Mum worked as Nurse"
    assert family["fact:me:1"]["end"] == "1975" and "fact:me:4" not in family
