"""Reading the old layout (people/*.md), which only `cronicl migrate` still does."""
import pytest

from cronicl.core.legacy import load_legacy_tree as load_tree
from cronicl.core.legacy import split_frontmatter
from cronicl.core.model import Event, Partnership, Person  # noqa: F401


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


def test_bad_partnership_shape_is_a_frontmatter_error(tmp_path, write):
    write(tmp_path, "people/x.md", "---\nname: X\npartnerships:\n  - with: [a, b]\n---\n")
    tree, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-BAD-FRONTMATTER"]
    assert tree.people == {}


def test_portrait_must_be_text(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nportrait: [a.jpg, b.jpg]\n---\n")
    _, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-BAD-FRONTMATTER"]


def test_events_as_one_mapping_and_bad_shapes(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nevents:\n  type: burial\n  date: 1991\n---\n")
    write(tmp_path, "people/b.md", "---\nname: B\nevents: [burial]\n---\n")
    tree, issues = load_tree(tmp_path)
    assert [(e.type, e.date) for e in tree.people["a"].events] == [("burial", "1991")]
    assert [(i.code, i.path) for i in issues if i.severity == "error"] == [("E-BAD-FRONTMATTER", "people/b.md")]


def test_gallery_id_must_be_text(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\ngallery_id: [a, b]\n---\n")
    _, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-BAD-FRONTMATTER"]


def test_duplicate_keys_in_front_matter_are_reported(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nbirth: 1950\nbirth: 1960\n---\n")
    tree, issues = load_tree(tmp_path)
    dup = [i for i in issues if i.code == "W-DUPLICATE-KEY"]
    assert len(dup) == 1 and "'birth'" in dup[0].message and dup[0].path == "people/a.md"
    assert tree.people["a"].birth.date == "1960"


def test_nested_duplicate_keys_are_reported(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname:\n  given: A\n  given: B\nevents:\n  - type: x\n    type: y\n---\n")
    _, issues = load_tree(tmp_path)
    assert [i.code for i in issues].count("W-DUPLICATE-KEY") == 2


def test_no_duplicates_no_warning(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nname: A\nbirth: 1950\n---\n")
    _, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.code == "W-DUPLICATE-KEY"] == []
