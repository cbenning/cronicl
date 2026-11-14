from datetime import date

import pytest

from famsite.model import Event, LifeEvent, Partnership, Person
from famsite.privacy import is_living, redact
from famsite.relations import build_relations
from famsite.render import build_site

TODAY = date(2026, 10, 10)


def p(pid, given, surname, **kw):
    return {"id": pid, "given": given, "surname": surname, **kw}


def family(make_tree):
    return make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920"), death=Event(date="1990")),
            p("brown-mary", "Mary", "Brown", birth=Event(date="1925"), death=Event(date="2001")),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1975"), parents=["smith-john", "brown-mary"],
              body="Bob bio", partnerships=[Partnership("zzjones-jane", type="marriage", start="2001", place="Elsewhere")]),
            p("zzjones-jane", "Jane", "Zzjones", birth=Event(date="1980")),
            p("smith-amy", "Amy", "Smith", birth=Event(date="2005"), parents=["smith-bob", "zzjones-jane"], body="Amy bio"),
        ]
    )


def test_is_living_rules():
    assert is_living(Person(id="x", birth=Event(date="1900")), TODAY) is False
    assert is_living(Person(id="x", birth=Event(date="1950")), TODAY) is True
    assert is_living(Person(id="x", birth=Event(date="1950"), death=Event(date="2000")), TODAY) is False
    assert is_living(Person(id="x"), TODAY) is True
    assert is_living(Person(id="x", birth=Event(date="1950"), living=False), TODAY) is False
    assert is_living(Person(id="x", birth=Event(date="1900"), living=True), TODAY) is True
    assert is_living(Person(id="x", birth=Event(date="not a date")), TODAY) is True
    assert is_living(Person(id="x", death=Event()), TODAY) is False


def test_full_mode_changes_nothing(make_tree):
    tree = family(make_tree)
    out = redact(tree, mode="full", today=TODAY)
    assert set(out.people) == set(tree.people)
    assert out.people["zzjones-jane"].given == "Jane"


def test_placeholder_mode_anonymizes_ids_names_and_bodies(make_tree):
    out = redact(family(make_tree), mode="placeholder", today=TODAY, salt="s3cret")
    assert "smith-bob" not in out.people and "zzjones-jane" not in out.people and "smith-amy" not in out.people
    living = [person for person in out.people.values() if person.given == "Living"]
    assert len(living) == 3  # bob, jane, amy
    for person in living:
        assert person.id.startswith("living-")
        assert person.birth is None and person.body == "" and person.surname is None
    assert out.people["smith-john"].given == "John"
    blob = repr(out.people)
    assert "Zzjones" not in blob and "zzjones" not in blob and "Jane" not in blob
    assert "Bob bio" not in blob and "Amy bio" not in blob and "Elsewhere" not in blob


def test_structure_survives_in_placeholder_mode(make_tree):
    out = redact(family(make_tree), mode="placeholder", today=TODAY, salt="s3cret")
    rel = build_relations(out)
    # Amy is the only person whose two parents are both anonymized (Bob and Jane).
    amy = next(
        pid for pid, parents in rel.parents.items()
        if len(parents) == 2 and all(x.startswith("living-") for x in parents)
    )
    assert amy.startswith("living-")
    # Bob, one of Amy's anonymized parents, still points at his real, non-living parents.
    bob = next(x for x in rel.parents[amy] if rel.parents[x] == ["smith-john", "brown-mary"])
    assert bob.startswith("living-")


def test_marriage_with_a_living_spouse_loses_its_details(make_tree):
    tree = make_tree(
        [
            p("old-x", "X", "Old", birth=Event(date="1900"), death=Event(date="1970"),
              partnerships=[Partnership("young-y", type="marriage", start="1960", place="Somewhere")]),
            p("young-y", "Y", "Young", birth=Event(date="1990")),
        ]
    )
    out = redact(tree, mode="placeholder", today=TODAY, salt="s")
    marriage = out.people["old-x"].partnerships[0]
    assert marriage.with_id.startswith("living-")
    assert marriage.start is None and marriage.place is None and marriage.type is None


def test_hidden_mode_removes_living_people_and_every_reference(make_tree):
    out = redact(family(make_tree), mode="hidden", today=TODAY, salt="s")
    assert set(out.people) == {"smith-john", "brown-mary"}
    for person in out.people.values():
        for ref in person.parents + person.spouse + person.children:
            assert ref in out.people
        for marriage in person.partnerships:
            assert marriage.with_id in out.people


def test_same_salt_gives_same_anonymous_ids(make_tree):
    a = redact(family(make_tree), mode="placeholder", today=TODAY, salt="x")
    b = redact(family(make_tree), mode="placeholder", today=TODAY, salt="x")
    c = redact(family(make_tree), mode="placeholder", today=TODAY, salt="y")
    assert sorted(a.people) == sorted(b.people)
    assert sorted(a.people) != sorted(c.people)


def test_unknown_mode_is_rejected(make_tree):
    with pytest.raises(ValueError):
        redact(family(make_tree), mode="nope", today=TODAY)


def test_ended_partnership_with_a_living_partner_loses_type_dates_and_note(make_tree):
    tree = make_tree(
        [
            p("old-x", "X", "Old", birth=Event(date="1900"), death=Event(date="1980"),
              partnerships=[
                  Partnership("young-y", type="marriage", start="1960", end="1970", end_reason="divorce", note="secret")
              ]),
            p("young-y", "Y", "Young", birth=Event(date="2000")),
        ]
    )
    out = redact(tree, mode="placeholder", today=TODAY, salt="s")
    entry = out.people["old-x"].partnerships[0]
    assert entry.with_id.startswith("living-")
    assert (entry.type, entry.start, entry.end, entry.end_reason, entry.note) == (None, None, None, None, None)


def test_a_living_persons_events_never_reach_the_output(tmp_path, make_tree):
    tree = make_tree([
        {"id": "old", "given": "Old", "birth": Event(date="1800"), "events": [LifeEvent(type="occupation", value="Blacksmith")]},
        {"id": "kid", "given": "Kid", "birth": Event(date="2000"), "parents": ["old"],
         "events": [LifeEvent(type="occupation", value="Zookeeper", date="2020", note="Secretnote", cite=["Secretsource"])]},
    ])
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=date(2026, 10, 10))
    everything = b"".join(f.read_bytes() for f in tmp_path.rglob("*") if f.is_file())
    assert b"Blacksmith" in everything
    for secret in (b"Zookeeper", b"Secretnote", b"Secretsource"):
        assert secret not in everything
