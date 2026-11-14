"""Regression tests for the whole-branch review findings (C1, I1-I8)."""
import os
from datetime import date

import pytest

from cronicl.checks import check_all as check_tree
from cronicl.cli import main
from cronicl.core.fix import FixPlan, apply_plan, plan_fix
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
    "front",
    [
        "sex: [M]",
        "id: [a]",
        "name: [Bob, Smith]",
        "birth: [1950]",
        "marriages:\n  - with: [x]",
        "parents: {a: b}",
        "living: [true]",
        "name:\n  given: [Bob]",
        "birth:\n  date: [1950]",
        "gedcom_id: [I1]",
    ],
)
def test_wrong_shaped_values_are_reported_not_crashed(tmp_path, write, front):
    write(tmp_path, "people/x.md", f"---\n{front}\n---\n")
    write(tmp_path, "people/good.md", "---\nname: Good\n---\n")
    tree, issues = load_tree(tmp_path)
    check_tree(tree, issues)  # must not raise
    assert "good" in tree.people
    assert "E-BAD-FRONTMATTER" in codes(issues)


# I2: fix must not drop nested unknown keys or partner-less marriage entries ------------------------


def test_fix_keeps_nested_unknown_keys_and_partnerless_marriages(tmp_path, write):
    write(
        tmp_path,
        "people/smith-bob.md",
        "---\nid: smith-bob\nname:\n  given: Bob\n  surname: Smith\n  nickname: Bobby\n"
        "birth:\n  date: 1950\n  note: hospital birth\n"
        "marriages:\n  - with: x\n    date: 1975\n    witness: Pat\n  - date: 1990\n    place: Reno\n---\n",
    )
    write(tmp_path, "people/x.md", "---\nid: x\nname: X\n---\n")
    apply_plan(plan_fix(tmp_path))
    assert plan_fix(tmp_path).empty
    tree, _ = load_tree(tmp_path)
    bob = tree.people["smith-bob"]
    assert bob.name_extra == {"nickname": "Bobby"}
    assert bob.birth.extra == {"note": "hospital birth"}
    assert bob.partnerships[0].with_id == "x" and bob.partnerships[0].extra == {"witness": "Pat"}
    assert len(bob.partnerships) == 2
    assert bob.partnerships[1].with_id == "" and bob.partnerships[1].start == "1990" and bob.partnerships[1].place == "Reno"


def test_partnerless_marriage_is_a_warning_not_a_dangling_reference(make_tree):
    tree = make_tree([{"id": "a", "given": "A", "partnerships": [Partnership("", type="marriage", start="1990", place="Reno")]}])
    assert codes(check_tree(tree)) == ["W-PARTNERSHIP-NO-PARTNER"]


# I3: duplicate invalid pinned ids must not be guessed ---------------------------------------------


def test_duplicate_invalid_pinned_ids_are_reported_and_references_untouched(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: Smith_Bob\nname: First\n---\n")
    write(tmp_path, "people/b.md", "---\nid: Smith_Bob\nname: Second\n---\n")
    write(tmp_path, "people/kid.md", "---\nname: Kid\nparents: [Smith_Bob]\n---\n")
    plan = plan_fix(tmp_path)
    assert "E-DUPLICATE-ID" in [i.code for i in plan.unresolved]
    apply_plan(plan)
    tree, _ = load_tree(tmp_path)
    assert tree.people["kid"].parents == ["Smith_Bob"]


# I4: a rename that targets the same file must not delete it ---------------------------------------


def test_apply_plan_does_not_unlink_a_path_that_is_the_same_file_as_a_write(tmp_path):
    old = tmp_path / "Bob.md"
    old.write_text("old", encoding="utf-8")
    new = tmp_path / "bob.md"
    os.link(old, new)  # stands in for a case-insensitive filesystem, where both names are one file
    apply_plan(FixPlan(writes={new: "new"}, deletes=[old]))
    assert new.read_text(encoding="utf-8") == "new"
    assert old.exists()


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


def test_build_prints_warnings(tmp_path, write, capsys):
    main(["init", "--legacy-layout", "--dir", str(tmp_path)])
    write(tmp_path, "people/bob.md", "---\nid: bob\nname: Bob\nbirth: sometime\n---\n")
    capsys.readouterr()
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert "W-DATE-UNPARSED" in capsys.readouterr().out
