from famsite.model import Event, Marriage, Person
from famsite.store import dump_person, load_tree, split_frontmatter


def test_loads_person_with_defaults(tmp_path, write):
    write(tmp_path, "people/smith-bob.md", "---\nname: Bob Smith\n---\nHello there\n")
    tree, issues = load_tree(tmp_path)
    person = tree.people["smith-bob"]
    assert (person.given, person.surname) == ("Bob", "Smith")
    assert person.body == "Hello there"
    assert person.id_pinned is False
    assert person.sex == "U"
    assert person.parents == [] and person.spouse == [] and person.children == [] and person.marriages == []


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
    assert person.marriages == [Marriage("c", "1975-06-20", "Surrey, BC")]


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
        marriages=[Marriage("e-f", "~1900", "Halifax, Nova Scotia: Canada")],
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
    assert loaded.marriages == [Marriage("e-f", "~1900", "Halifax, Nova Scotia: Canada")]
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
    write(tmp_path, "site.yml", "schema_version: 2\n")
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
