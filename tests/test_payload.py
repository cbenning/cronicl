from datetime import date

import pytest

from famsite.model import Event, LifeEvent, Partnership
from famsite.privacy import redact
from famsite.render import life_summary, person_payload


def p(pid, given, surname=None, **kw):
    return {"id": pid, "given": given, "surname": surname, **kw}


def family(make_tree):
    return make_tree(
        [
            p("dad", "Dan", "Roe", birth=Event(date="1920-03-01"), death=Event(date="1990-02-28")),
            p("mum", "Mia", "Roe", birth=Event(date="1925")),
            p("ex", "Eve", "Poe"),
            p("kid", "Kay", "Roe", parents=["dad", "mum"], birth=Event(date="1950-06")),
            p("full", "Fay", "Roe", parents=["dad", "mum"], birth=Event(date="1952")),
            p("half", "Hal", "Roe", parents=["dad", "ex"], birth=Event(date="1955")),
            p("lone", "Lou", "Roe", parents=["dad"], birth=Event(date="1957")),
        ]
    )


def test_refs_carry_years_and_initials(make_tree):
    payload = person_payload(family(make_tree), "kid")
    dad = next(r for r in payload["parents"] if r["id"] == "dad")
    assert dad == {"id": "dad", "name": "Dan Roe", "years": "1920–1990", "initials": "DR"}


def test_siblings_are_typed_with_the_shared_parents(make_tree):
    siblings = {s["id"]: s for s in person_payload(family(make_tree), "kid")["siblings"]}
    assert siblings["full"]["type"] == "full"
    assert [v["id"] for v in siblings["full"]["via"]] == ["dad", "mum"]
    assert siblings["half"]["type"] == "half"
    assert [v["id"] for v in siblings["half"]["via"]] == ["dad"]
    # one side has only one known parent: nothing is inferred about the other parent
    assert siblings["lone"]["type"] == "sibling"
    assert [v["id"] for v in siblings["lone"]["via"]] == ["dad"]


def test_siblings_sort_by_birth_year_then_name(make_tree):
    ids = [s["id"] for s in person_payload(family(make_tree), "kid")["siblings"]]
    assert ids == ["full", "half", "lone"]


def test_initials_image_and_age_at_death(make_tree):
    payload = person_payload(family(make_tree), "dad")
    assert payload["initials"] == "DR"
    assert payload["image"] is None
    assert payload["age_at_death"] == 69
    assert payload["age_at_death_approx"] is False
    assert person_payload(family(make_tree), "mum")["age_at_death"] is None


def test_age_at_death_is_flagged_when_a_date_is_approximate(make_tree):
    tree = make_tree([p("a", "Al", birth=Event(date="~1900"), death=Event(date="1970"))])
    payload = person_payload(tree, "a")
    assert (payload["age_at_death"], payload["age_at_death_approx"]) == (70, True)


def test_nameless_person_has_question_mark_initials(make_tree):
    tree = make_tree([{"id": "unknown-i1"}])
    assert person_payload(tree, "unknown-i1")["initials"] == "?"


def test_placeholder_redaction_gives_l_and_hides_names_in_siblings_via(make_tree):
    tree = make_tree(
        [
            p("old", "Olga", "Zzold", birth=Event(date="1900"), death=Event(date="1970")),
            p("me", "Moe", "Qqme", birth=Event(date="1990"), parents=["old"]),
            p("sib", "Sid", "Wwsib", birth=Event(date="1992"), parents=["old"]),
        ]
    )
    out = redact(tree, mode="placeholder", today=date(2026, 10, 15), salt="s")
    living = next(pid for pid in out.people if pid.startswith("living-"))
    payload = person_payload(out, living)
    assert payload["initials"] == "L"
    assert payload["name"] == "Living"
    assert all("Qqme" not in str(v) and "Wwsib" not in str(v) for v in payload.values())


def test_payload_events_are_dated_rows_with_text_and_age(make_tree):
    payload = person_payload(family(make_tree), "dad")
    ev = {e["id"]: e for e in payload["events"]}
    assert ev["birth:dad"]["text"] == "born" and ev["birth:dad"]["role"] == "self"
    assert ev["death:dad"]["age"] == 69 and ev["death:dad"]["year"] == 1990
    assert ev["birth:kid"]["role"] == "child" and ev["birth:kid"]["text"] == "Kay Roe born"
    assert [e["year"] for e in payload["events"]] == sorted(e["year"] for e in payload["events"])


def test_payload_carries_worded_dates(make_tree):
    tree = make_tree([
        {"id": "a", "given": "Ann", "birth": Event(date="1941-03-12", place="Guelph"),
         "death": Event(date="APR 4 TH 2020"),
         "partnerships": [Partnership("b", type="marriage", start="1955-06-20", end="1990-02", end_reason="divorce")]},
        {"id": "b", "given": "Bob"},
    ])
    payload = person_payload(tree, "a")
    assert payload["birth"] == {"date": "1941-03-12", "place": "Guelph", "when": "12 March 1941"}
    assert payload["death"]["when"] == "APR 4 TH 2020"
    assert [e["when"] for e in payload["events"]] == ["12 March 1941", "20 June 1955", "February 1990"]
    assert payload["spouses"][0]["partnerships"][0]["text"] == "Married 20 June 1955 – divorced February 1990"


def pl(birth=None, death=None, age=None, approx=False):
    return {"birth": birth, "death": death, "age_at_death": age, "age_at_death_approx": approx}


@pytest.mark.parametrize("payload, expected", [
    (pl({"when": "12 March 1941", "place": "Guelph, Ontario"}, {"when": "4 June 2021", "place": None}, 80),
     "Born 12 March 1941 in Guelph, Ontario. Died 4 June 2021, aged 80."),
    (pl({"when": "about 1907", "place": None}), "Born about 1907."),
    (pl({"when": "", "place": "Guelph"}), "Born in Guelph."),
    (pl({"when": "about 1907", "place": None}, {"when": "1990", "place": "Surrey, BC"}, 83, True),
     "Born about 1907. Died 1990 in Surrey, BC, aged about 83."),
    (pl(None, {"when": "APR 4 TH 2020", "place": None}), "Died APR 4 TH 2020."),
    (pl({"when": "", "place": None}, None), ""),
    (pl(), ""),
])
def test_life_summary(payload, expected):
    assert life_summary(payload) == expected


def test_payload_has_summary(make_tree):
    tree = make_tree([{"id": "a", "given": "Ann", "birth": Event(date="1941-03-12", place="Guelph")}])
    assert person_payload(tree, "a")["summary"] == "Born 12 March 1941 in Guelph."


def fact_tree(make_tree):
    return make_tree([{
        "id": "a", "given": "Ann",
        "birth": Event(date="1920", extra={"cite": "Parish register", "note": "At home"}),
        "events": [
            LifeEvent(type="occupation", value="Carpenter <b>", note="Self-employed", cite=["Census 1911"]),
            LifeEvent(type="graduation"),
            LifeEvent(type="residence", start="1960-05", end="1975", place="Surrey", cite=["Directory"]),
        ],
    }])


def test_payload_facts_notes_and_cites(make_tree):
    payload = person_payload(fact_tree(make_tree), "a")
    assert payload["facts"] == [
        {"label": "Occupation", "text": "Carpenter <b>", "note": "Self-employed", "cite": ["Census 1911"]},
        {"label": "Graduation", "text": "", "note": None, "cite": []},
    ]
    birth, lived = payload["events"]
    assert (birth["note"], birth["cite"]) == ("At home", ["Parish register"])
    assert (lived["when"], lived["text"], lived["place"], lived["cite"]) == ("May 1960 – 1975", "lived", "Surrey", ["Directory"])
