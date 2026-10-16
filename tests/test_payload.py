from datetime import date

from famsite.model import Event
from famsite.privacy import redact
from famsite.render import person_payload


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
