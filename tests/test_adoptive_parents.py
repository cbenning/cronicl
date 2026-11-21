"""`adoptive-parents`: a second link up from the child, kept apart from the birth `parents`, and its GEDCOM mapping."""
from datetime import date

from cronicl.cli import main
from cronicl.core.gedcom import import_nodes, parse_nodes, write_import_family
from cronicl.core.gedcom_export import export_gedcom
from cronicl.core.relations import build_relations
from cronicl.core.show import describe
from cronicl.core.store import load_tree

TODAY = date(2026, 11, 15)

FAMILY = """\
smith-john:
  name: {given: John, surname: Smith}
  sex: male
  birth: 1930
brown-mary:
  name: {given: Mary, surname: Brown}
  sex: female
  birth: 1932
smith-john + brown-mary:
  events:
    - {type: marriage, date: 1955}
kowalski-eva:
  name: {given: Eva, surname: Kowalski}
  sex: female
  birth: 1940
smith-anna:
  name: {given: Anna, surname: Smith}
  birth: 1960
  adoptive-parents: [smith-john, brown-mary]
  events:
    - {type: adoption, date: 1962, place: Guelph}
smith-ben:
  name: {given: Ben, surname: Smith}
  birth: 1961
  parents: [kowalski-eva]
  adoptive-parents: [smith-john, brown-mary]
  events:
    - {type: adoption}
"""


def load(tmp_path, write_family, text=FAMILY):
    folder = tmp_path / "fam"
    write_family(folder, text)
    return load_tree(folder)


def codes(issues):
    return sorted(i.code for i in issues)


def test_the_tree_draws_a_child_under_the_adoptive_parents(tmp_path, write_family):
    from cronicl.checks import check_all

    tree, issues = load(tmp_path, write_family)
    rel = build_relations(tree)
    assert not [i for i in check_all(tree, issues) if "adoptive" in i.message or i.severity == "error"]
    assert rel.parents["smith-anna"] == ["smith-john", "brown-mary"]
    assert rel.adoptive_parents["smith-anna"] == ["smith-john", "brown-mary"]
    assert rel.birth_parents["smith-anna"] == []
    # birth parents are known too: the tree still uses the adoptive family, both kinds stay readable
    assert rel.parents["smith-ben"] == ["smith-john", "brown-mary"]
    assert rel.birth_parents["smith-ben"] == ["kowalski-eva"]
    assert rel.kids["brown-mary+smith-john"] == ["smith-anna", "smith-ben"]


def test_a_person_without_adoptive_parents_is_unchanged(make_tree):
    tree = make_tree([{"id": "a"}, {"id": "b"}, {"id": "c", "parents": ["a", "b"]}])
    rel = build_relations(tree)
    assert rel.parents["c"] == rel.birth_parents["c"] == ["a", "b"]
    assert rel.adoptive_parents["c"] == []


def test_dangling_too_many_and_repeated_adoptive_parents_are_reported(tmp_path, write_family):
    text = (
        "a:\n  name: {given: A}\nb:\n  name: {given: B}\nc:\n  name: {given: C}\n"
        "kid:\n  name: {given: Kid}\n  adoptive-parents: [a, b, c]\n"
        "kid2:\n  name: {given: Kid2}\n  adoptive-parents: [a, a]\n"
        "kid3:\n  name: {given: Kid3}\n  adoptive-parents: [nobody]\n"
    )
    tree, issues = load(tmp_path, write_family, text)
    build = build_relations(tree).issues
    assert "W-TOO-MANY-ADOPTIVE-PARENTS" in codes(build)
    assert "E-DANGLING-REF" in codes(build)
    from cronicl.checks import check_all

    assert "W-DUPLICATE-PARENT" in codes(check_all(tree, issues))


def test_adoptive_parents_must_be_a_list(tmp_path, write_family):
    _, issues = load(tmp_path, write_family, "a:\n  name: {given: A}\nkid:\n  name: {given: K}\n  adoptive-parents: a\n")
    assert "E-RECORD-SHAPE" in codes(issues)


def test_a_nameless_birth_parent_is_still_a_parent(tmp_path, write_family):
    text = FAMILY + "unknown-father:\nsmith-cara:\n  name: {given: Cara}\n  parents: [unknown-father]\n  adoptive-parents: [smith-john]\n"
    _, issues = load(tmp_path, write_family, text)
    from cronicl.checks import check_all

    tree, _ = load_tree(tmp_path / "fam")
    assert "W-NO-NAME" not in codes(check_all(tree))


def test_adopters_dates_do_not_bound_a_birth(tmp_path, write_family):
    from cronicl.checks import check_all

    text = (
        "old:\n  name: {given: Old}\n  birth: 1900\n  death: 1950\n"
        "kid:\n  name: {given: Kid}\n  birth: 1960\n  adoptive-parents: [old]\n"
    )
    write_family(tmp_path / "fam", text)
    tree, _ = load_tree(tmp_path / "fam")
    assert "W-CHILD-AFTER-PARENT-DEATH" not in codes(check_all(tree))
    write_family(tmp_path / "fam2", text.replace("adoptive-parents", "parents"))
    tree, _ = load_tree(tmp_path / "fam2")
    assert "W-CHILD-AFTER-PARENT-DEATH" in codes(check_all(tree))


def test_show_labels_adoptive_and_birth_parents(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family)
    text = describe(tree, build_relations(tree), "smith-ben")
    assert "adoptive parents: John Smith (smith-john), Mary Brown (brown-mary)" in text
    assert "birth parents: Eva Kowalski (kowalski-eva)" in text


def test_new_takes_adoptive_parents(tmp_path, write_family, capsys):
    folder = tmp_path / "fam"
    write_family(folder, FAMILY)
    assert main(["new", "--dir", str(folder), "--given", "Dan", "--adoptive-parents", "smith-john", "brown-mary", "-a"]) == 0
    tree, _ = load_tree(folder)
    assert tree.people["dan"].adoptive_parents == ["smith-john", "brown-mary"]


def test_rename_follows_adoptive_parents(tmp_path, write_family, capsys):
    folder = tmp_path / "fam"
    write_family(folder, FAMILY)
    assert main(["rename", "--dir", str(folder), "smith-john", "smith-jon", "-a"]) == 0
    tree, _ = load_tree(folder)
    assert tree.people["smith-anna"].adoptive_parents == ["smith-jon", "brown-mary"]


# ---- GEDCOM ----------------------------------------------------------------------------------------------------

BOTH = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Brown/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Eva /Kowalski/
1 SEX F
1 FAMS @F2@
0 @I4@ INDI
1 NAME Ben /Smith/
1 FAMC @F2@
2 PEDI birth
1 FAMC @F1@
2 PEDI adopted
1 ADOP
2 DATE 12 MAR 1962
2 PLAC Guelph
2 FAMC @F1@
3 ADOP BOTH
0 @I5@ INDI
1 NAME Anna /Smith/
1 FAMC @F1@
2 PEDI adopted
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I4@
1 CHIL @I5@
0 @F2@ FAM
1 WIFE @I3@
1 CHIL @I4@
0 TRLR
"""


def by_name(result):
    return {p.given: p for p in result.people}


def import_text(text):
    nodes, _ = parse_nodes(text)
    return import_nodes(nodes)


def test_import_maps_pedi_adopted_to_adoptive_parents():
    result = import_text(BOTH)
    people = by_name(result)
    john, mary = people["John"].id, people["Mary"].id
    ben, anna = people["Ben"], people["Anna"]
    assert ben.parents == [people["Eva"].id]
    assert sorted(ben.adoptive_parents) == sorted([john, mary])
    assert anna.parents == [] and sorted(anna.adoptive_parents) == sorted([john, mary])
    assert not [i for i in result.issues if i.code in ("W-CHIL-CONFLICT", "W-CHIL-WITHOUT-FAMC", "W-DANGLING-FAMC")]


def test_import_turns_adop_into_an_adoption_event_without_leftovers():
    ben = by_name(import_text(BOTH))["Ben"]
    event = next(e for e in ben.events if e.type == "adoption")
    assert (event.date, event.place) == ("1962-03-12", "Guelph")
    assert not ben.gedcom_extra  # the FAMC under ADOP and PEDI lines are mapped, not set aside


def test_import_uses_the_family_an_adop_event_names():
    text = (
        "0 @I1@ INDI\n1 NAME A /B/\n0 @I2@ INDI\n1 NAME C /D/\n1 FAMC @F1@\n1 ADOP\n2 FAMC @F1@\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n0 TRLR\n"
    )
    people = by_name(import_text(text))
    # a FAMC with no PEDI that the ADOP event names is the adoptive family
    assert people["C"].parents == [] and people["C"].adoptive_parents == [people["A"].id]


def test_import_does_not_link_a_foster_family_as_birth_parents():
    text = (
        "0 @I1@ INDI\n1 NAME A /B/\n0 @I2@ INDI\n1 NAME C /D/\n1 FAMC @F1@\n2 PEDI foster\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n0 TRLR\n"
    )
    result = import_text(text)
    kid = by_name(result)["C"]
    assert not kid.parents and not kid.adoptive_parents
    assert "2 PEDI foster" in kid.gedcom_extra
    assert "W-PEDI-UNMAPPED" in {i.code for i in result.issues}
    assert "W-CHIL-CONFLICT" not in {i.code for i in result.issues} and "W-CHIL-WITHOUT-FAMC" not in {i.code for i in result.issues}


def test_a_foster_link_beside_a_birth_family_leaves_the_birth_family_alone():
    text = (
        "0 @I1@ INDI\n1 NAME A /B/\n0 @I2@ INDI\n1 NAME E /F/\n0 @I3@ INDI\n1 NAME C /D/\n"
        "1 FAMC @F1@\n1 FAMC @F2@\n2 PEDI foster\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I3@\n0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I3@\n0 TRLR\n"
    )
    people = by_name(import_text(text))
    assert people["C"].parents == [people["A"].id] and not people["C"].adoptive_parents


ADOPTED_BY_ONE = """\
0 @I1@ INDI
1 NAME Hal /Reed/
1 SEX M
0 @I2@ INDI
1 NAME Ida /Reed/
1 SEX F
0 @I3@ INDI
1 NAME Kit /Reed/
1 FAMC @F1@
2 PEDI adopted
1 ADOP
2 FAMC @F1@
3 ADOP {who}
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


def test_adop_husb_or_wife_names_the_one_parent_who_adopted():
    for who, name in (("HUSB", "Hal"), ("WIFE", "Ida")):
        people = by_name(import_text(ADOPTED_BY_ONE.format(who=who)))
        assert people["Kit"].adoptive_parents == [people[name].id], who
        assert not people["Kit"].gedcom_extra, who  # the line is mapped, not set aside


def test_adop_both_names_both_parents():
    people = by_name(import_text(ADOPTED_BY_ONE.format(who="BOTH")))
    assert sorted(people["Kit"].adoptive_parents) == sorted([people["Hal"].id, people["Ida"].id])


def test_import_does_not_call_a_second_valid_family_a_conflict():
    result = import_text(BOTH)
    assert "W-CHIL-CONFLICT" not in {i.code for i in result.issues}


def export(tree):
    text, issues = export_gedcom(tree, today=TODAY)
    return text, issues


def test_export_writes_both_famc_links_birth_first(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family)
    text, _ = export(tree)
    ben = text.split("1 NAME Ben /Smith/")[1].split("\n0 ")[0]
    lines = ben.splitlines()
    famc = [i for i, line in enumerate(lines) if line.startswith("1 FAMC")]
    assert len(famc) == 2
    assert lines[famc[0] + 1] == "2 PEDI birth" and lines[famc[1] + 1] == "2 PEDI adopted"
    anna = text.split("1 NAME Anna /Smith/")[1].split("\n0 ")[0]
    assert "2 PEDI adopted" in anna and "2 PEDI birth" not in anna  # one family only: the default needs no word
    assert "1 ADOP\n2 DATE 1962\n2 PLAC Guelph\n2 FAMC @F" in text


def test_a_birth_family_alone_gets_no_pedi(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family, "a:\n  name: {given: A}\nb:\n  name: {given: B}\n  parents: [a]\n")
    text, _ = export(tree)
    assert "PEDI" not in text


def test_export_writes_a_lone_adoptive_parent_as_a_one_spouse_family(tmp_path, write_family):
    text = "a:\n  name: {given: A}\n  sex: female\nk:\n  name: {given: K}\n  adoptive-parents: [a]\n"
    tree, _ = load(tmp_path, write_family, text)
    out, _ = export(tree)
    assert "0 @F1@ FAM\n1 WIFE @I1@\n1 CHIL @I2@" in out
    assert "2 PEDI adopted" in out


def shape(tree):
    names = {pid: p.display_name for pid, p in tree.people.items()}
    return {
        names[pid]: (
            tuple(sorted(names[x] for x in p.parents)),
            tuple(sorted(names[x] for x in p.adoptive_parents)),
            [(e.type, e.date, e.place) for e in p.events],
        )
        for pid, p in tree.people.items()
    }


def reimport(tree, tmp_path):
    text, _ = export(tree)
    result = import_text(text)
    folder = tmp_path / "again"
    folder.mkdir()
    (folder / "site.yml").write_text("title: T\nschema_version: 3\n", encoding="utf-8")
    write_import_family(result, folder, text.encode("utf-8"), "export.ged")
    again, issues = load_tree(folder)
    assert not [i for i in issues if i.severity == "error"], issues
    return again


def test_adoptive_parents_survive_export_then_import(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family)
    again = reimport(tree, tmp_path)
    assert shape(again) == shape(tree)


def test_a_gedcom_with_adoption_exports_and_imports_to_the_same_family(tmp_path):
    first = import_text(BOTH)
    folder = tmp_path / "one"
    folder.mkdir()
    (folder / "site.yml").write_text("title: T\nschema_version: 3\n", encoding="utf-8")
    write_import_family(first, folder, BOTH.encode("utf-8"), "t.ged")
    tree, _ = load_tree(folder)
    assert shape(reimport(tree, tmp_path)) == shape(tree)


def test_a_living_adoptive_parent_is_still_a_placeholder_link(tmp_path, write_family):
    text = (
        "pat-lee:\n  name: {given: Pat, surname: Lee}\n  living: true\n"
        "kid-one:\n  name: {given: Kid}\n  birth: 1900\n  death: 1950\n  adoptive-parents: [pat-lee]\n"
    )
    tree, _ = load(tmp_path, write_family, text)
    out, _ = export_gedcom(tree, mode="placeholder", today=TODAY)
    assert "1 NAME Living" in out
    assert "Pat" not in out and "Lee" not in out
    kid = out.split("1 NAME Kid")[1].split("\n0 ")[0]
    assert "1 FAMC" in kid and "2 PEDI adopted" in kid


def test_the_editor_palette_offers_adoptive_parents_until_there_are_two():
    from cronicl.tui.screens.palette import build_entries

    def labels(**kw):
        return [e.label for e in build_entries("person", set(), kw.get("parents", 0), None, None, kw.get("adoptive", 0))]

    assert "adoptive-parents" in labels() and "parents" in labels()
    assert "adoptive-parents" not in labels(adoptive=2) and "parents" in labels(adoptive=2)
    assert "parents" not in labels(parents=2) and "adoptive-parents" in labels(parents=2)


# ---- the generated site ------------------------------------------------------------------------------------------


def test_raised_elsewhere_lists_birth_children_an_adoptive_family_raised(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family)
    rel = build_relations(tree)
    assert rel.raised_elsewhere["kowalski-eva"] == ["smith-ben"]
    assert rel.raised_elsewhere["smith-john"] == []


def test_the_layout_marks_only_the_adopted_edges(tmp_path, write_family):
    from cronicl.site.layout import compute_layout

    tree, _ = load(tmp_path, write_family)
    edges = {e["to"]: e for e in compute_layout(tree)["edges"] if e["kind"] == "child"}
    assert edges["smith-anna"]["adopted"] is True and edges["smith-ben"]["adopted"] is True
    tree2, _ = load(tmp_path / "plain", write_family, "a:\n  name: {given: A}\nb:\n  name: {given: B}\n  parents: [a]\n")
    assert all("adopted" not in e for e in compute_layout(tree2)["edges"])


def test_the_person_payload_says_who_adopted_and_who_gave_birth(tmp_path, write_family):
    from cronicl.site.render import person_payload

    tree, _ = load(tmp_path, write_family)
    ben = person_payload(tree, "smith-ben")
    assert [(r["id"], r["note"]) for r in ben["parents"]] == [("smith-john", "adoptive parent"), ("brown-mary", "adoptive parent")]
    assert [(r["id"], r["note"]) for r in ben["birth_parents"]] == [("kowalski-eva", "birth parent")]
    assert ben["raised_elsewhere"] == []
    assert person_payload(tree, "smith-anna")["birth_parents"] == []
    john = person_payload(tree, "smith-john")
    assert {r["id"]: r["note"] for r in john["children"]} == {"smith-anna": "adopted", "smith-ben": "adopted"}
    eva = person_payload(tree, "kowalski-eva")
    assert [(r["id"], r["note"]) for r in eva["raised_elsewhere"]] == [("smith-ben", "adopted by others")]
    assert eva["children"] == []


def test_the_built_person_page_shows_both_families(tmp_path, write_family):
    from cronicl.site.render import build_site

    tree, _ = load(tmp_path, write_family)
    out = tmp_path / "out"
    build_site(tree, out, today=TODAY)
    ben = (out / "p" / "smith-ben" / "index.html").read_text(encoding="utf-8")
    assert "Birth parents" in ben and "adoptive parent" in ben and "Kowalski" in ben
    eva = (out / "p" / "kowalski-eva" / "index.html").read_text(encoding="utf-8")
    assert "Children raised by others" in eva and "adopted by others" in eva
    john = (out / "p" / "smith-john" / "index.html").read_text(encoding="utf-8")
    assert "Birth parents" not in john and "Children raised by others" not in john


def test_the_viewer_draws_adopted_edges_dotted():
    from pathlib import Path

    import cronicl

    viewer = Path(cronicl.__file__).parent / "site" / "viewer"
    assert ".edge.adopted" in (viewer / "style.css").read_text(encoding="utf-8")
    assert "edge.adopted ? ' adopted'" in (viewer / "viewer.js").read_text(encoding="utf-8")
