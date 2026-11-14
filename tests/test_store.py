from famsite.model import Event, Partnership, Person
from famsite.store import dump_person, load_tree, split_frontmatter


def test_loads_person_with_defaults(tmp_path, write):
    write(tmp_path, "people/smith-bob.md", "---\nname: Bob Smith\n---\nHello there\n")
    tree, issues = load_tree(tmp_path)
    person = tree.people["smith-bob"]
    assert (person.given, person.surname) == ("Bob", "Smith")
    assert person.body == "Hello there"
    assert person.id_pinned is False
    assert person.sex == "U"
    assert person.parents == [] and person.spouse == [] and person.children == [] and person.partnerships == []


def test_explicit_id_is_kept_and_pinned(tmp_path, write):
    write(tmp_path, "people/whatever.md", "---\nid: smith-bob\nname: Bob Smith\n---\n")
    tree, _ = load_tree(tmp_path)
    assert "smith-bob" in tree.people
    assert tree.people["smith-bob"].id_pinned is True


def test_implicit_id_is_normalized_stem(tmp_path, write):
    write(tmp_path, "people/Smith Bob.md", "---\nname: Bob Smith\n---\n")
    tree, _ = load_tree(tmp_path)
    assert "smith-bob" in tree.people


def test_relationship_fields_accept_flow_block_and_scalar_forms(tmp_path, write):
    write(
        tmp_path,
        "people/x.md",
        "---\nname: X\nparents: [a, b]\nspouse: c\nchildren:\n  - d\n  - e\n"
        "marriages:\n  - with: c\n    date: 1975-06-20\n    place: Surrey, BC\n---\n",
    )
    tree, _ = load_tree(tmp_path)
    person = tree.people["x"]
    assert person.parents == ["a", "b"]
    assert person.spouse == ["c"]
    assert person.children == ["d", "e"]
    assert person.partnerships == [Partnership("c", type="marriage", start="1975-06-20", place="Surrey, BC")]


def test_roundtrip_tricky_values(tmp_path, write):
    # Review focus 1: commas, colons and apostrophes in places, including marriages.
    person = Person(
        id="no-null",
        given="Null",
        surname="No",
        birth=Event(date="1066", place="St. John's: Newfoundland, Canada"),
        death=Event(),
        parents=["a-b", "c-d"],
        spouse=["e-f"],
        children=["g-h"],
        partnerships=[Partnership("e-f", type="marriage", start="~1900", place="Halifax, Nova Scotia: Canada")],
        body="First paragraph.\n\nSecond paragraph.",
        extra={"media": ["a.jpg", "b.jpg"]},
        gedcom_id="I12",
        gedcom_extra="1 OCCU Teacher\n2 DATE BET 1975 AND 1990",
    )
    write(tmp_path, "people/no-null.md", dump_person(person))
    tree, issues = load_tree(tmp_path)
    loaded = tree.people["no-null"]
    assert (loaded.given, loaded.surname) == ("Null", "No")
    assert loaded.birth == Event(date="1066", place="St. John's: Newfoundland, Canada")
    assert loaded.death is not None and loaded.death.is_empty()
    assert loaded.parents == ["a-b", "c-d"]
    assert loaded.spouse == ["e-f"]
    assert loaded.children == ["g-h"]
    assert loaded.partnerships == person.partnerships
    assert loaded.body == person.body
    assert loaded.extra == {"media": ["a.jpg", "b.jpg"]}
    assert loaded.gedcom_extra == person.gedcom_extra
    assert loaded.gedcom_id == "I12"


def test_yaml_autotyping_is_not_applied(tmp_path, write):
    # Review focus 2: hand-written YAML must not turn No/Null/1066 into bool/None/int.
    write(
        tmp_path,
        "people/x.md",
        "---\nname:\n  given: Null\n  surname: No\nbirth:\n  date: 1066\n  place: 1066\nliving: no\n---\n",
    )
    tree, _ = load_tree(tmp_path)
    person = tree.people["x"]
    assert (person.given, person.surname) == ("Null", "No")
    assert person.birth == Event(date="1066", place="1066")
    assert person.living is False


def test_handles_crlf_and_bom(tmp_path, write):
    write(tmp_path, "people/smith-bob.md", "﻿---\r\nname: Bob Smith\r\n---\r\nBody text\r\n")
    tree, issues = load_tree(tmp_path)
    person = tree.people["smith-bob"]
    assert person.given == "Bob"
    assert person.body == "Body text"


def test_broken_frontmatter_reports_issue_and_does_not_crash(tmp_path, write):
    # Review focus 4.
    write(tmp_path, "people/bad.md", "---\nname: [unclosed\n---\nbody\n")
    write(tmp_path, "people/good.md", "---\nname: Good Person\n---\n")
    write(tmp_path, "people/list.md", "---\n- a\n- b\n---\n")
    tree, issues = load_tree(tmp_path)
    assert "good" in tree.people
    assert "bad" not in tree.people
    assert [i.code for i in issues].count("E-BAD-FRONTMATTER") == 2


def test_duplicate_ids_are_reported_and_first_wins(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: smith-bob\nname: First\n---\n")
    write(tmp_path, "people/b.md", "---\nid: smith-bob\nname: Second\n---\n")
    tree, issues = load_tree(tmp_path)
    assert tree.people["smith-bob"].given == "First"
    assert [i.code for i in issues if i.severity == "error"] == ["E-DUPLICATE-ID"]


def test_missing_site_yml_is_a_warning(tmp_path):
    tree, issues = load_tree(tmp_path)
    assert [i.code for i in issues] == ["W-NO-SITE-YML"]
    assert issues[0].severity == "warning"


def test_site_yml_schema_version_is_checked(tmp_path, write):
    write(tmp_path, "site.yml", "schema_version: 3\n")
    _, issues = load_tree(tmp_path)
    assert "E-SCHEMA-VERSION" in [i.code for i in issues]


def test_dump_is_stable_and_readable():
    person = Person(
        id="smith-bob",
        given="Bob",
        surname="Smith",
        sex="M",
        birth=Event(date="1950-03-12", place="Vancouver, BC"),
        living=False,
        parents=["smith-john", "brown-mary"],
        body="Bio.",
    )
    first = dump_person(person)
    front, body = split_frontmatter(first)
    assert body == "Bio."
    assert front["id"] == "smith-bob"
    assert front["parents"] == ["smith-john", "brown-mary"]
    assert dump_person(person) == first
    assert "parents:\n  - smith-john\n  - brown-mary\n" in first


def test_legacy_marriages_load_as_marriage_partnerships(tmp_path, write):
    write(
        tmp_path,
        "people/x.md",
        "---\nname: X\nmarriages:\n  - with: c\n    date: 1975-06-20\n    place: Surrey, BC\n---\n",
    )
    tree, _ = load_tree(tmp_path)
    assert tree.people["x"].partnerships == [
        Partnership("c", type="marriage", start="1975-06-20", place="Surrey, BC")
    ]


def test_partnerships_read_every_field(tmp_path, write):
    write(
        tmp_path,
        "people/x.md",
        "---\nname: X\npartnerships:\n  - with: c\n    type: marriage\n    start: 1955\n    end: 1971\n"
        "    end_reason: divorce\n    place: Reno\n    note: Second marriage\n    witness: Pat\n---\n",
    )
    tree, _ = load_tree(tmp_path)
    assert tree.people["x"].partnerships == [
        Partnership(
            "c", type="marriage", start="1955", end="1971", end_reason="divorce",
            place="Reno", note="Second marriage", extra={"witness": "Pat"},
        )
    ]


def test_start_wins_over_legacy_date_and_both_lists_load(tmp_path, write):
    write(
        tmp_path,
        "people/x.md",
        "---\nname: X\npartnerships:\n  - with: c\n    date: 1950\n    start: 1951\n"
        "marriages:\n  - with: d\n    date: 1960\n---\n",
    )
    tree, _ = load_tree(tmp_path)
    got = tree.people["x"].partnerships
    assert [(p.with_id, p.start) for p in got] == [("c", "1951"), ("d", "1960")]
    assert got[1].type == "marriage"
    assert got[0].type is None


def test_partnerships_are_written_in_block_style_and_roundtrip(tmp_path, write):
    person = Person(
        id="x",
        given="X",
        partnerships=[
            Partnership("c", type="marriage", start="1955", end="unknown", end_reason="divorce", place="Reno, NV: USA"),
            Partnership("d", note="no dates"),
        ],
    )
    text = dump_person(person)
    assert "marriages:" not in text and "{" not in text and "[" not in text
    assert "  - with: c\n    type: marriage\n    start: 1955\n    end: unknown\n    end_reason: divorce\n" in text
    write(tmp_path, "people/x.md", text)
    tree, _ = load_tree(tmp_path)
    assert tree.people["x"].partnerships == person.partnerships


def test_bad_partnership_shape_is_a_frontmatter_error(tmp_path, write):
    write(tmp_path, "people/x.md", "---\nname: X\npartnerships:\n  - with: [a, b]\n---\n")
    tree, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-BAD-FRONTMATTER"]
    assert tree.people == {}


def test_portrait_round_trips(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: a\nname:\n  given: Ann\nliving: false\nportrait: scans/ann 1.jpg\nparents: []\n---\nBio.\n")
    tree, _ = load_tree(tmp_path)
    person = tree.people["a"]
    assert person.portrait == "scans/ann 1.jpg" and "portrait" not in person.extra
    text = dump_person(person)
    assert "living: false\nportrait: scans/ann 1.jpg\n" in text


def test_portrait_must_be_text(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nportrait: [a.jpg, b.jpg]\n---\n")
    _, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-BAD-FRONTMATTER"]


PERSON_WITH_EVENTS = """---
id: a
name:
  given: Ann
events:
  - type: occupation
    value: Carpenter
    cite: Census 1911
  - type: immigration
    date: 1952-04
    place: Halifax, NS
    note: Aboard the Arosa Kulm
    cite:
      - Passenger list
      - Family letter
    ship: Arosa Kulm
---
"""


def test_events_round_trip(tmp_path, write):
    write(tmp_path, "people/a.md", PERSON_WITH_EVENTS)
    tree, _ = load_tree(tmp_path)
    person = tree.people["a"]
    assert [(e.type, e.date, e.place, e.value, e.note, e.cite, e.extra) for e in person.events] == [
        ("occupation", None, None, "Carpenter", None, ["Census 1911"], {}),
        ("immigration", "1952-04", "Halifax, NS", None, "Aboard the Arosa Kulm", ["Passenger list", "Family letter"], {"ship": "Arosa Kulm"}),
    ]
    assert "events" not in person.extra
    again, _ = split_frontmatter(dump_person(person))
    assert again["events"][0] == {"type": "occupation", "value": "Carpenter", "cite": ["Census 1911"]}
    assert again["events"][1]["ship"] == "Arosa Kulm" and list(again["events"][1])[:2] == ["type", "date"]


def test_events_as_one_mapping_and_bad_shapes(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nevents:\n  type: burial\n  date: 1991\n---\n")
    write(tmp_path, "people/b.md", "---\nname: B\nevents: [burial]\n---\n")
    tree, issues = load_tree(tmp_path)
    assert [(e.type, e.date) for e in tree.people["a"].events] == [("burial", "1991")]
    assert [(i.code, i.path) for i in issues if i.severity == "error"] == [("E-BAD-FRONTMATTER", "people/b.md")]
