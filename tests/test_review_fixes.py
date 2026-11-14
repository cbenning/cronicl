"""Regression tests for the whole-branch review findings (C1, I1-I8)."""
import os
from datetime import date

import pytest

from cronicl.checks import check_all as check_tree
from cronicl.cli import main
from cronicl.core.gedcom import import_nodes, parse_nodes
from cronicl.site.layout import LayoutError, compute_layout
from cronicl.core.model import Event, Partnership
from cronicl.site.render import build_site
from cronicl.core.store import load_tree

TODAY = date(2026, 10, 10)


def from_text(text):
    nodes, _ = parse_nodes(text)
    return import_nodes(nodes)


def codes(issues):
    return sorted(i.code for i in issues)


# C1: stale output must not survive a rebuild ---------------------------------------------------


def test_rebuild_removes_stale_output_for_a_person_who_became_living(tmp_path, make_tree):
    def tree(living):
        t = make_tree(
            [
                {
                    "id": "smith-bob", "given": "Bob", "surname": "Smith",
                    "birth": Event(date="1950"), "living": living, "body": "Bio of Bob",
                }
            ]
        )
        t.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
        return t

    out = tmp_path / "out"
    build_site(tree(False), out, today=TODAY)
    assert (out / "data/people/smith-bob.json").exists()
    build_site(tree(None), out, today=TODAY)  # born 1950, no death: living
    assert not (out / "data/people/smith-bob.json").exists()
    assert not (out / "p/smith-bob").exists()
    for f in out.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            assert "Bob" not in text and "smith-bob" not in text and "Bio of Bob" not in text, f


def test_rebuild_leaves_unrelated_files_in_the_output_directory(tmp_path, make_tree):
    out = tmp_path / "out"
    out.mkdir()
    (out / "CNAME").write_text("example.org\n", encoding="utf-8")
    build_site(make_tree([{"id": "a", "given": "A"}]), out, today=TODAY)
    assert (out / "CNAME").read_text(encoding="utf-8") == "example.org\n"


# I1: wrong-shaped values must be reported, never crash --------------------------------------------


@pytest.mark.parametrize(
    "record",
    [
        "x:\n  sex: [male]\n",
        "x:\n  name: [Bob, Smith]\n",
        "x:\n  birth: [1950]\n",
        "x:\n  parents: {a: b}\n",
        "x:\n  living: [true]\n",
        "x:\n  name:\n    given: [Bob]\n",
        "x:\n  birth:\n    date: [1950]\n",
        "x:\n  refs: {gedcom: [I1]}\n",
        "x:\n  events: [[a], {type: [t]}]\n",
        "x + good:\n  events: [[marriage]]\n",
        "x + good:\n  note: [a]\n",
        "[x]: y\n",
    ],
)
def test_wrong_shaped_values_are_reported_not_crashed(tmp_path, write_family, record):
    write_family(tmp_path, record + "good:\n  name: {given: Good}\n")
    tree, issues = load_tree(tmp_path)
    check_tree(tree, issues)  # must not raise
    assert "good" in tree.people or "E-BAD-FAMILY" in codes(issues)


# I2: fix must not drop nested unknown keys or partner-less marriage entries ------------------------




def test_partnerless_marriage_is_a_warning_not_a_dangling_reference(make_tree):
    tree = make_tree([{"id": "a", "given": "A", "partnerships": [Partnership("", type="marriage", start="1990", place="Reno")]}])
    assert codes(check_tree(tree)) == ["W-PARTNERSHIP-NO-PARTNER"]


# I3: duplicate invalid pinned ids must not be guessed ---------------------------------------------




# I4: a rename that targets the same file must not delete it ---------------------------------------




# I5: cross-generation marriages must be reported at check time and named by layout ----------------


def stepfamily(make_tree):
    return make_tree(
        [
            {"id": "w", "given": "w"},
            {"id": "h1", "given": "h1"},
            {"id": "h2", "given": "h2"},
            {"id": "d", "given": "d", "parents": ["w", "h1"]},
            {"id": "k", "given": "k", "parents": ["w", "h2"]},
            {"id": "g", "given": "g", "parents": ["d", "h2"]},
        ]
    )


def test_generation_conflict_is_an_error_in_check(make_tree):
    issues = check_tree(stepfamily(make_tree))
    assert "E-GENERATION-CONFLICT" in codes(issues)
    assert "E-CYCLE" not in codes(issues)


def test_layout_error_names_the_unions_involved(make_tree):
    with pytest.raises(LayoutError, match=r"d\+h2"):
        compute_layout(stepfamily(make_tree))


# I6: GEDCOM sub-records of mapped tags must be preserved -------------------------------------------


def test_gedcom_subrecords_of_mapped_tags_are_preserved():
    person = from_text(
        "0 @I1@ INDI\n1 NAME A /B/\n1 SEX X\n"
        "1 BIRT\n2 DATE 1950\n3 SOUR @S1@\n2 PLAC Vancouver\n3 MAP\n4 LATI N49\n4 LONG W123\n"
        "1 NOTE a note\n2 SOUR @S2@\n"
        "1 FAMC @F1@\n2 PEDI adopted\n"
        "0 @F1@ FAM\n1 CHIL @I1@\n0 TRLR\n"
    ).people[0]
    for needle in ["3 SOUR @S1@", "3 MAP", "4 LATI N49", "4 LONG W123", "2 SOUR @S2@", "2 PEDI adopted", "1 SEX X"]:
        assert needle in person.gedcom_extra, needle
    assert person.birth.date == "1950" and person.birth.place == "Vancouver"
    assert person.sex == "U"


# I7: a dangling CHIL is reported, preserved, and does not hide the couple --------------------------


def test_dangling_chil_is_reported_preserved_and_does_not_hide_the_couple():
    result = from_text(
        "0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I99@\n0 TRLR\n"
    )
    assert "W-DANGLING-CHILD" in codes(result.issues)
    owner = next(p for p in result.people if p.gedcom_id == "I1")
    assert owner.spouse == ["y-b"]
    assert "1 CHIL @I99@" in owner.gedcom_extra


# I8: build prints warnings -------------------------------------------------------------------------


def test_build_prints_warnings(tmp_path, write_family, capsys):
    write_family(tmp_path, "bob:\n  name: {given: Bob}\n  birth: sometime\n")
    capsys.readouterr()
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert "W-DATE-UNPARSED" in capsys.readouterr().out


# Final-review fixes ---------------------------------------------------------------------------------------


def _couples(tmp_path, write_family, couple_events):
    write_family(tmp_path, f"a:\n  name: {{given: A}}\nb:\n  name: {{given: B}}\na + b:\n  events:\n{couple_events}")
    from cronicl.core.relations import build_relations

    tree, _ = load_tree(tmp_path)
    return build_relations(tree).couples["a+b"]


def test_married_divorced_married_again_without_dates_is_two_partnerships_and_not_ended(tmp_path, write_family):
    couple = _couples(tmp_path, write_family, "    - {type: marriage}\n    - {type: divorce}\n    - {type: marriage}\n")
    assert len(couple.partnerships) == 2 and couple.ended is False


def test_a_dated_second_marriage_keeps_its_own_dates(tmp_path, write_family):
    couple = _couples(
        tmp_path, write_family, "    - {type: marriage, place: Bath}\n    - {type: divorce, date: 1830}\n    - {type: marriage, date: 1840}\n"
    )
    assert [(p.start, p.end) for p in couple.partnerships] == [(None, "1830"), ("1840", None)] and couple.ended is False


def test_separation_then_divorce_is_one_ended_partnership_with_no_conflict_warning(tmp_path, write_family):
    couple = _couples(
        tmp_path, write_family, "    - {type: marriage, date: 1820}\n    - {type: separation, date: 1826}\n    - {type: divorce, date: 1828}\n"
    )
    assert [(p.start, p.end, p.end_reason) for p in couple.partnerships] == [("1820", "1828", "divorce")]
    tree, issues = load_tree(tmp_path)
    assert "W-PARTNERSHIP-CONFLICT" not in codes(check_tree(tree, issues))


def _edit(tmp_path, text, fn, pid="smith"):
    from cronicl.core import inplace

    return getattr(inplace, fn)(text, pid)


@pytest.mark.parametrize("tail", ["", "   # todo"])
def test_mark_living_on_a_blank_living_line_writes_valid_yaml(tmp_path, write_family, tail):
    text = f"smith:\n  name: {{given: A}}\n  living:{tail}\n  bio: hi\n"
    out = _edit(tmp_path, text, "set_living")
    write_family(tmp_path, out)
    tree, issues = load_tree(tmp_path)
    assert "E-BAD-FAMILY" not in codes(issues) and tree.people["smith"].living is True


def test_birth_with_swapped_bet_years_still_counts_as_the_later_year():
    from cronicl.core.dates import latest_year

    assert latest_year("BET 1990 AND 1900") == 1990


def test_living_false_does_not_make_a_recently_born_person_public(tmp_path, write_family):
    write_family(tmp_path, "kid:\n  name: {given: Kid}\n  birth: 1990\n  living: false\n")
    tree, _ = load_tree(tmp_path)
    from cronicl.core.living import is_living

    assert is_living(tree.people["kid"], TODAY) is True


def test_an_insert_lands_under_its_own_record_not_under_the_next_ones_comment(tmp_path):
    text = "smith:\n  name: {given: A}\n  birth: 1950\n\n# ---- Jones line ----\njones:\n  name: {given: J}\n"
    for fn, line in (("set_living", "living: true"), ("set_death_unknown", "death: unknown")):
        out = _edit(tmp_path, text, fn)
        lines = out.splitlines()
        assert lines.index("  " + line) < lines.index("# ---- Jones line ----"), (fn, out)
