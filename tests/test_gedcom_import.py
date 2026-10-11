import random

import pytest

from famsite.gedcom import (
    ImportRefused,
    decode_gedcom,
    import_nodes,
    parse_nodes,
    write_import,
)
from famsite.model import Marriage
from famsite.relations import build_relations
from famsite.store import load_tree


def load_result(path):
    data = path.read_bytes()
    nodes, _ = parse_nodes(decode_gedcom(data))
    return import_nodes(nodes), data


def by_gedcom_id(items):
    return {item.gedcom_id: item for item in items}


def from_text(text):
    nodes, _ = parse_nodes(text)
    return import_nodes(nodes)


def test_ids_are_slugged_and_collisions_numbered(sample_ged):
    result, _ = load_result(sample_ged)
    assert {p.gedcom_id: p.id for p in result.people} == {
        "I1": "smith-bob",
        "I2": "jones-jane",
        "I3": "smith-amy",
        "I4": "smith-tom",
        "I5": "smith-john",
        "I6": "brown-mary",
        "I7": "smith-bob-2",
        "I8": "unknown-i8",
    }
    assert result.families == 2


def test_person_fields_are_mapped(sample_ged):
    result, _ = load_result(sample_ged)
    people = by_gedcom_id(result.people)
    bob = people["I1"]
    assert (bob.given, bob.surname, bob.sex) == ("Bob", "Smith", "M")
    assert bob.birth.date == "1950-03-12" and bob.birth.place == "Vancouver, BC"
    assert bob.death.date == "2020-07-01" and bob.death.place == "Burnaby, BC"
    assert bob.parents == ["smith-john", "brown-mary"]
    assert bob.body == "Bob was a teacher\nwho loved the sea."
    assert "1 OCCU Teacher" in bob.gedcom_extra
    assert "2 DATE BET 1975 AND 1990" in bob.gedcom_extra
    assert people["I2"].birth.date == "~1952"
    assert people["I3"].death is not None and people["I3"].death.is_empty()
    assert people["I3"].parents == ["smith-bob", "jones-jane"]
    assert people["I4"].parents == ["smith-bob", "jones-jane"]


def test_marriage_goes_on_the_partner_with_the_smallest_id(sample_ged):
    result, _ = load_result(sample_ged)
    people = by_gedcom_id(result.people)
    assert people["I2"].marriages == [Marriage("smith-bob", "1975-06-20", "Surrey, BC")]
    assert people["I1"].marriages == []
    assert people["I1"].spouse == [] and people["I2"].spouse == []


def test_skipped_records_are_counted_and_no_errors(sample_ged):
    result, _ = load_result(sample_ged)
    assert result.skipped == {"HEAD": 1, "TRLR": 1}
    assert [i for i in result.issues if i.severity == "error"] == []


def test_import_is_independent_of_record_order(sample_ged):
    nodes, _ = parse_nodes(decode_gedcom(sample_ged.read_bytes()))
    expected = {p.gedcom_id: (p.id, p.parents) for p in import_nodes(nodes).people}
    shuffled = list(nodes)
    random.Random(7).shuffle(shuffled)
    assert {p.gedcom_id: (p.id, p.parents) for p in import_nodes(shuffled).people} == expected


def test_unparsable_dates_are_kept_and_warned():
    result = from_text("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE BET 1900 AND 1910\n0 TRLR\n")
    assert result.people[0].birth.date == "BET 1900 AND 1910"
    assert [i.code for i in result.issues] == ["W-DATE-UNPARSED"]


def test_chil_without_famc_sets_parents_and_warns():
    result = from_text(
        "0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /X/\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n0 TRLR\n"
    )
    child = by_gedcom_id(result.people)["I2"]
    assert child.parents == [by_gedcom_id(result.people)["I1"].id]
    assert "W-CHIL-WITHOUT-FAMC" in [i.code for i in result.issues]


def test_childless_unmarried_family_becomes_a_spouse_entry_and_keeps_fam_extras():
    result = from_text(
        "0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 DIV Y\n0 TRLR\n"
    )
    people = by_gedcom_id(result.people)
    owner = people["I1"]  # smallest id: x-a < y-b
    assert owner.id == "x-a"
    assert owner.spouse == ["y-b"]
    assert "0 @F1@ FAM" in owner.gedcom_extra
    assert "1 DIV Y" in owner.gedcom_extra


def test_marriage_data_with_one_partner_is_preserved_as_extra():
    result = from_text(
        "0 @I1@ INDI\n1 NAME A /X/\n0 @F1@ FAM\n1 HUSB @I1@\n1 MARR\n2 DATE 1900\n0 TRLR\n"
    )
    person = result.people[0]
    assert person.marriages == []
    assert "1 MARR" in person.gedcom_extra and "2 DATE 1900" in person.gedcom_extra


def test_second_famc_goes_to_extra():
    result = from_text(
        "0 @I0@ INDI\n1 NAME P /Q/\n0 @I9@ INDI\n1 NAME R /S/\n"
        "0 @I1@ INDI\n1 NAME A /X/\n1 FAMC @F1@\n1 FAMC @F2@\n"
        "0 @F1@ FAM\n1 HUSB @I0@\n1 CHIL @I1@\n0 @F2@ FAM\n1 HUSB @I9@\n1 CHIL @I1@\n0 TRLR\n"
    )
    person = by_gedcom_id(result.people)["I1"]
    assert person.parents == [by_gedcom_id(result.people)["I0"].id]
    assert "1 FAMC @F2@" in person.gedcom_extra


@pytest.mark.parametrize(
    "name,given,surname",
    [
        ("Mary /de la Cruz/", "Mary", "de la Cruz"),
        ("/Smith/", None, "Smith"),
        ("Madonna", "Madonna", None),
        ("John /Smith/ Jr", "John Jr", "Smith"),
    ],
)
def test_name_shapes(name, given, surname):
    person = from_text(f"0 @I1@ INDI\n1 NAME {name}\n0 TRLR\n").people[0]
    assert (person.given, person.surname) == (given, surname)


def test_write_import_creates_files_and_archive(tmp_path, sample_ged):
    result, data = load_result(sample_ged)
    summary = write_import(result, tmp_path, data, "sample.ged")
    assert summary["people"] == 8 and summary["families"] == 2
    assert (tmp_path / "people" / "smith-bob.md").exists()
    assert not (tmp_path / "unions").exists()
    assert summary["archive"].endswith(".ged")
    tree, issues = load_tree(tmp_path)
    rel = build_relations(tree)
    assert rel.kids["jones-jane+smith-bob"] == ["smith-amy", "smith-tom"]
    assert rel.couples["jones-jane+smith-bob"].marriage.date == "1975-06-20"
    assert [i for i in issues + rel.issues if i.severity == "error"] == []


def test_write_import_refuses_when_already_imported(tmp_path, sample_ged):
    result, data = load_result(sample_ged)
    write_import(result, tmp_path, data, "sample.ged")
    with pytest.raises(ImportRefused):
        write_import(result, tmp_path, data, "sample.ged")
