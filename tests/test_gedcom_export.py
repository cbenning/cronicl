from datetime import date

import pytest

from cronicl.cli import main
from cronicl.core.gedcom_export import export_gedcom, read_gedcom_extra
from cronicl.core.store import load_tree

from gedcom_check import problems

TODAY = date(2026, 11, 15)

FAMILY = """\
byron-george:
  name: {given: George, surname: Byron}
  sex: male
  birth: {date: 1788-01-22, place: "London, England", cite: Baptism register}
  death: {date: 1824-04-19, place: "Missolonghi, Greece"}
milbanke-annabella:
  name: {given: Annabella, surname: Milbanke, also: [Lady Byron]}
  sex: female
  birth: 1792-05-17
  death: unknown
byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02, place: "Seaham, England", note: Winter wedding, cite: Marriage bond}
    - {type: separation, date: 1816}
lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace, prefix: Lady, nickname: Ada}
  sex: female
  birth: {date: 1815-12-10, note: Born at Piccadilly Terrace.}
  death: {date: 1852-11-27}
  parents: [byron-george, milbanke-annabella]
  events:
    - {type: occupation, value: Mathematician, cite: [Letters, Babbage notes]}
    - {type: residence, date: FROM 1835 TO 1852, place: "Ockham Park, Surrey"}
    - {type: pilgrimage, date: ABT 1840, place: Rome}
  bio: |
    Mathematician and writer. Mail: ada@example.org

    She is often described as the first programmer.
king-william:
  name: {given: William, surname: King}
  sex: male
  birth: 1805
king-william + lovelace-ada:
  events:
    - {type: marriage, date: 1835-07-08}
    - {type: divorce, date: 1850}
    - {type: marriage, date: 1851}
lone-parent-child:
  name: {given: Lone}
  parents: [king-william]
"""


@pytest.fixture
def family(tmp_path, write_family):
    write_family(tmp_path, FAMILY)
    tree, _ = load_tree(tmp_path)
    return tree


def export(tree, **kw):
    kw.setdefault("today", TODAY)
    return export_gedcom(tree, **kw)[0]


def test_the_output_is_structurally_valid_gedcom(family):
    text = export(family)
    assert problems(text) == []
    for needle in ("1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED", "1 CHAR UTF-8", "0 @SUBM@ SUBM"):
        assert needle in text


def test_names_sex_dates_places_and_events(family):
    text = export(family)
    assert "1 NAME Augusta Ada /Lovelace/\n2 GIVN Augusta Ada\n2 SURN Lovelace\n2 NPFX Lady\n2 NICK Ada" in text
    assert "1 NAME Lady Byron\n2 TYPE aka" in text
    assert "1 BIRT\n2 DATE 22 JAN 1788\n2 PLAC London, England" in text
    assert "1 DEAT Y" in text  # death: unknown
    assert "1 OCCU Mathematician" in text
    assert "1 RESI\n2 DATE FROM 1835 TO 1852\n2 PLAC Ockham Park, Surrey" in text
    assert "1 EVEN\n2 TYPE pilgrimage\n2 DATE ABT 1840\n2 PLAC Rome" in text
    assert "1 SEX F" in text and "1 SEX M" in text


def test_multiline_bio_uses_cont_and_at_signs_are_doubled(family):
    text = export(family)
    assert "1 NOTE Mathematician and writer. Mail: ada@@example.org\n2 CONT\n2 CONT She is often described as the first programmer." in text


def test_a_very_long_value_is_split_with_conc_and_reads_back_whole(tmp_path, write_family):
    long = "word " * 200
    write_family(tmp_path, f"a:\n  name: {{given: A}}\n  bio: {long.strip()}\n")
    tree, _ = load_tree(tmp_path)
    text = export(tree)
    assert problems(text) == [] and "CONC" in text
    from cronicl.core.gedcom import import_nodes, parse_nodes

    assert import_nodes(parse_nodes(text)[0]).people[0].body == long.strip()


def test_families_one_per_partnership_with_children_on_the_first(family):
    text = export(family)
    assert text.count("0 @F") == 4  # byron+milbanke, king+lovelace twice, king alone (lone-parent-child)
    assert "1 MARR\n2 DATE 2 JAN 1815\n2 PLAC Seaham, England\n2 NOTE Winter wedding\n2 SOUR @S" in text
    assert "1 EVEN\n2 TYPE separation\n2 DATE 1816" in text
    assert "1 DIV\n2 DATE 1850" in text
    assert text.count("1 MARR") == 3
    assert text.count("1 CHIL") == 2  # ada under her parents, the lone child under william


def test_sources_become_records_once_each(family):
    text = export(family)
    titles = [l for l in text.split("\n") if l.startswith("1 TITL")]
    assert sorted(titles) == sorted(["1 TITL Baptism register", "1 TITL Marriage bond", "1 TITL Letters", "1 TITL Babbage notes"])


def test_xrefs_keep_refs_gedcom_when_present_and_are_unique(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n  refs: {gedcom: I7}\nb:\n  name: {given: B}\n  refs: {gedcom: I7}\nc:\n  name: {given: C}\n")
    tree, _ = load_tree(tmp_path)
    text = export(tree)
    assert problems(text) == []
    assert text.count("0 @I7@ INDI") == 1 and text.count("INDI") == 3


def _living_family(tmp_path, write_family):
    write_family(
        tmp_path,
        "old:\n  name: {given: Old, surname: Timer}\n  birth: 1850\n  death: 1920\n"
        "kid:\n  name: {given: Secretname, surname: Livingperson}\n  birth: 2015\n  parents: [old]\n  bio: private words\n"
        "  events:\n    - {type: residence, place: Hiddenplace, cite: Hidden source}\n",
    )
    tree, _ = load_tree(tmp_path)
    return tree


def test_placeholder_privacy_keeps_a_nameless_node_with_links(tmp_path, write_family):
    text = export(_living_family(tmp_path, write_family), mode="placeholder")
    assert problems(text) == []
    assert "1 NAME Living" in text and "Secretname" not in text and "Livingperson" not in text
    for secret in ("private words", "Hiddenplace", "Hidden source", "2015"):
        assert secret not in text
    assert "1 FAMC @F1@" in text


def test_hidden_privacy_leaves_living_people_out_entirely(tmp_path, write_family):
    text = export(_living_family(tmp_path, write_family), mode="hidden")
    assert problems(text) == [] and "Living" not in text and "Secretname" not in text and text.count("INDI") == 1
    assert "FAM" not in text.replace("FAMILY", "")


def test_include_living_exports_everyone(tmp_path, write_family):
    text = export(_living_family(tmp_path, write_family), mode="hidden", include_living=True)
    assert "Secretname" in text and "private words" in text


def test_places_with_coordinates_get_a_map(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n  birth: {date: 1900, place: Hamburg}\n")
    tree, _ = load_tree(tmp_path)
    text = export(tree, places={"hamburg": (53.5511, -9.9937)})
    assert "2 PLAC Hamburg\n3 MAP\n4 LATI N53.5511\n4 LONG W9.9937" in text


def test_extra_lines_come_back_under_their_person(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n")
    tree, _ = load_tree(tmp_path)
    extra = read_gedcom_extra("a: |\n  1 SEX X\n  1 _MYTAG hello\n  2 NOTE deep\n")
    text = export(tree, extra=extra)
    assert "1 _MYTAG hello\n2 NOTE deep" in text and problems(text) == []


def test_cli_stdout_out_file_and_refusal(tmp_path, write_family, capsys):
    write_family(tmp_path, FAMILY)
    capsys.readouterr()
    assert main(["export-gedcom", "--dir", str(tmp_path)]) == 0
    assert problems(capsys.readouterr().out) == []
    target = tmp_path / "out.ged"
    assert main(["export-gedcom", "--dir", str(tmp_path), "--out", str(target)]) == 0
    assert problems(target.read_text(encoding="utf-8")) == []
    before = target.read_bytes()
    assert main(["export-gedcom", "--dir", str(tmp_path), "--out", str(target)]) == 2
    assert target.read_bytes() == before


def test_cli_refuses_a_family_with_errors(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n  parents: [ghost]\n")
    assert main(["export-gedcom", "--dir", str(tmp_path)]) == 1


def test_set_aside_lines_that_point_at_other_records_are_not_written(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n")
    tree, _ = load_tree(tmp_path)
    extra = read_gedcom_extra(
        "a: |\n  1 SOUR @S9@\n  2 PAGE 12\n  1 FAMC @F2@\n  2 PEDI adopted\n  1 _TAG kept\n  1 NOTE mail me@example.org\n  1 OBJE @https://x.example/@\n"
    )
    text, issues = export_gedcom(tree, today=TODAY, extra=extra)
    assert problems(text) == []
    assert "@S9@" not in text and "@F2@" not in text and "PEDI" not in text and "PAGE 12" not in text
    assert "1 _TAG kept" in text and "1 NOTE mail me@@example.org" in text
    assert [i.code for i in issues] == ["W-GEDCOM-EXTRA-POINTER"]


def test_reimporting_escaped_set_aside_text_gives_the_original_back(tmp_path):
    from cronicl.core.gedcom import import_nodes, parse_nodes

    ged = tmp_path / "x.ged"
    ged.write_text("0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME A /B/\n1 _MAIL me@@example.org\n0 TRLR\n", encoding="utf-8")
    first = import_nodes(parse_nodes(ged.read_text(encoding="utf-8"))[0]).people[0]
    assert "me@example.org" in first.gedcom_extra
    from cronicl.core.model import Tree

    tree = Tree()
    tree.people["b-a"] = first
    text, _ = export_gedcom(tree, today=TODAY, extra={"b-a": first.gedcom_extra})
    assert "1 _MAIL me@@example.org" in text and problems(text) == []
    again = import_nodes(parse_nodes(text)[0]).people[0]
    assert again.gedcom_extra == first.gedcom_extra


def test_cli_prints_one_line_per_kind_of_warning(tmp_path, write_family, capsys):
    write_family(tmp_path, "a:\n  name: {given: A}\nb:\n  name: {given: B}\n")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "gedcom-extra.yml").write_text("a: |\n  0 FAM @F1@\n  1 NOTE x\nb: |\n  0 FAM @F2@\n  1 NOTE y\n", encoding="utf-8")
    capsys.readouterr()
    assert main(["export-gedcom", "--dir", str(tmp_path), "--out", str(tmp_path / "o.ged")]) == 0
    err = capsys.readouterr().err
    assert err.count("W-GEDCOM-EXTRA-FAM") == 1 and "2 times" in err
