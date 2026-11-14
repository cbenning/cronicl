import random

import pytest

from cronicl.core.gedcom import (
    ImportRefused,
    decode_gedcom,
    import_nodes,
    parse_nodes,
    write_import,
)
from cronicl.core.model import Partnership
from cronicl.core.relations import build_relations
from cronicl.core.store import load_tree


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
    assert people["I2"].partnerships == [
        Partnership("smith-bob", type="marriage", start="1975-06-20", place="Surrey, BC")
    ]
    assert people["I1"].partnerships == []
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


FAM_HEAD = "0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"


def owner_of(text):
    return by_gedcom_id(from_text(text).people)["I1"]


def test_childless_family_with_only_a_divorce_is_a_marriage_that_ended():
    owner = owner_of(FAM_HEAD + "1 DIV Y\n0 TRLR\n")
    assert owner.id == "x-a"
    assert owner.partnerships == [Partnership("y-b", type="marriage", end="unknown", end_reason="divorce")]
    assert owner.spouse == []
    assert not owner.gedcom_extra


def test_div_date_becomes_end_on_the_marriage_partnership():
    owner = owner_of(
        FAM_HEAD + "1 MARR\n2 DATE 1 JAN 1950\n2 PLAC Reno\n1 DIV\n2 DATE 5 MAR 1960\n0 TRLR\n"
    )
    assert owner.partnerships == [
        Partnership("y-b", type="marriage", start="1950-01-01", end="1960-03-05", end_reason="divorce", place="Reno")
    ]
    assert owner.spouse == []


def test_div_without_a_date_is_an_unknown_end_and_keeps_other_lines():
    owner = owner_of(FAM_HEAD + "1 DIV Y\n2 PLAC Elko\n0 TRLR\n")
    assert owner.partnerships == [Partnership("y-b", type="marriage", end="unknown", end_reason="divorce")]
    assert "2 PLAC Elko" in owner.gedcom_extra


def test_div_n_is_not_a_divorce():
    owner = owner_of(FAM_HEAD + "1 DIV N\n0 TRLR\n")
    assert owner.partnerships == []
    assert owner.spouse == ["y-b"]
    assert "1 DIV N" in owner.gedcom_extra


def test_annulment_and_engagement():
    annulled = owner_of(FAM_HEAD + "1 MARR\n2 DATE 1950\n1 ANUL\n2 DATE 1951\n0 TRLR\n")
    assert annulled.partnerships == [
        Partnership("y-b", type="marriage", start="1950", end="1951", end_reason="annulment")
    ]
    engaged = owner_of(FAM_HEAD + "1 ENGA\n2 DATE 1949\n0 TRLR\n")
    assert engaged.partnerships == [Partnership("y-b", type="engagement", start="1949")]


def test_enga_next_to_marr_stays_in_extra():
    owner = owner_of(FAM_HEAD + "1 MARR\n2 DATE 1950\n1 ENGA\n2 DATE 1949\n0 TRLR\n")
    assert [(p.type, p.start) for p in owner.partnerships] == [("marriage", "1950")]
    assert "1 ENGA" in owner.gedcom_extra and "2 DATE 1949" in owner.gedcom_extra


def test_bare_marr_invents_nothing_but_marr_y_is_a_marriage():
    bare = owner_of(FAM_HEAD + "1 MARR\n0 TRLR\n")
    assert bare.partnerships == [] and bare.spouse == ["y-b"]
    asserted = owner_of(FAM_HEAD + "1 MARR Y\n0 TRLR\n")
    assert asserted.partnerships == [Partnership("y-b", type="marriage")]


def test_marriage_data_with_one_partner_is_preserved_as_extra():
    result = from_text(
        "0 @I1@ INDI\n1 NAME A /X/\n0 @F1@ FAM\n1 HUSB @I1@\n1 MARR\n2 DATE 1900\n0 TRLR\n"
    )
    person = result.people[0]
    assert person.partnerships == []
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
    assert rel.couples["jones-jane+smith-bob"].partnerships[0].start == "1975-06-20"
    assert [i for i in issues + rel.issues if i.severity == "error"] == []


def test_write_import_refuses_when_already_imported(tmp_path, sample_ged):
    result, data = load_result(sample_ged)
    write_import(result, tmp_path, data, "sample.ged")
    with pytest.raises(ImportRefused):
        write_import(result, tmp_path, data, "sample.ged")


def test_engagement_next_to_a_divorce_without_marriage_is_not_lost():
    owner = owner_of(FAM_HEAD + "1 ENGA\n2 DATE 1949\n2 PLAC Paris\n1 DIV\n2 DATE 1960\n0 TRLR\n")
    assert owner.partnerships == [Partnership("y-b", type="marriage", end="1960", end_reason="divorce")]
    assert "1 ENGA" in owner.gedcom_extra
    assert "2 DATE 1949" in owner.gedcom_extra and "2 PLAC Paris" in owner.gedcom_extra


def test_bare_or_note_only_div_asserts_nothing():
    for body in ("1 DIV\n", "1 DIV\n2 NOTE maybe\n"):
        owner = owner_of(FAM_HEAD + body + "0 TRLR\n")
        assert owner.partnerships == [], body
        assert owner.spouse == ["y-b"], body
        assert "1 DIV" in owner.gedcom_extra, body


def test_a_real_divorce_after_div_n_is_still_mapped():
    owner = owner_of(FAM_HEAD + "1 DIV N\n1 DIV\n2 DATE 1960\n0 TRLR\n")
    assert owner.partnerships == [Partnership("y-b", type="marriage", end="1960", end_reason="divorce")]
    assert "1 DIV N" in owner.gedcom_extra


def test_n_payload_wins_over_a_date_child():
    owner = owner_of(FAM_HEAD + "1 DIV N\n2 DATE 1960\n0 TRLR\n")
    assert owner.partnerships == []
    assert "1 DIV N" in owner.gedcom_extra


GED_EVENTS = """0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ann /Dunn/
1 OCCU Carpenter
1 IMMI
2 DATE APR 1952
2 PLAC Halifax
1 BURI
2 DATE 1991
1 RESI
2 DATE 1960
1 RESI
2 DATE 1970
1 FACT Left-handed
0 TRLR
"""


def test_individual_events_are_imported():
    result = from_text(GED_EVENTS)
    ann = next(p for p in result.people if p.given == "Ann")
    assert [(e.type, e.date, e.place, e.value) for e in ann.events] == [
        ("occupation", None, None, "Carpenter"), ("immigration", "1952-04", "Halifax", None),
        ("burial", "1991", None, None), ("residence", "1960", None, None), ("residence", "1970", None, None)]
    assert "FACT Left-handed" in (ann.gedcom_extra or "") and "OCCU" not in (ann.gedcom_extra or "")


def test_text_on_an_event_line_is_kept_as_a_note():
    result = from_text("0 HEAD\n0 @I1@ INDI\n1 NAME Ann /Dunn/\n1 RESI Marital status: married\n2 DATE 1960\n1 IMMI Y\n1 CENS\n0 TRLR\n")
    ann = next(p for p in result.people if p.given == "Ann")
    assert [(e.type, e.note) for e in ann.events] == [("residence", "Marital status: married"), ("immigration", None), ("census", None)]
