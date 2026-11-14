import pytest

from cronicl.cli import main
from cronicl.core.dates import from_gedcom, parse_date, parse_span
from cronicl.core.gedcom import ImportRefused, import_nodes, parse_nodes, write_import_family
from cronicl.core.store import load_tree


def run(*argv):
    return main([str(a) for a in argv])


@pytest.mark.parametrize(
    "gedcom, expected",
    [
        ("12 MAR 1950", "1950-03-12"),
        ("MAR 1950", "1950-03"),
        ("1950", "1950"),
        ("ABT 1850", "ABT 1850"),
        ("abt 12 mar 1850", "ABT 1850-03-12"),
        ("CAL 1850", "CAL 1850"),
        ("EST MAR 1850", "EST 1850-03"),
        ("BEF 1920", "BEF 1920"),
        ("AFT 3 JAN 1880", "AFT 1880-01-03"),
        ("BET 1880 AND 1890", "BET 1880 AND 1890"),
        ("bet mar 1880 and 12 dec 1890", "BET 1880-03 AND 1890-12-12"),
        ("FROM 1900 TO 1950", "FROM 1900 TO 1950"),
        ("from jan 1900", "FROM 1900-01"),
        ("TO 1950", "TO 1950"),
    ],
)
def test_gedcom_dates_convert_to_the_new_grammar(gedcom, expected):
    assert from_gedcom(gedcom) == (expected, True)
    assert parse_date(expected) is not None or parse_span(expected) is not None


@pytest.mark.parametrize("gedcom", ["32 MAR 1950", "@#DJULIAN@ 12 MAR 1750", "1750/51", "12 1950", "BET 1900", "FROM", "ABT ABT 1850", "FROM ABT 1900 TO 1950", "BET 1900 AND", ""])
def test_unconvertible_gedcom_dates_stay_as_written(gedcom):
    assert from_gedcom(gedcom) == (gedcom.strip(), False)


def import_text(tmp_path, gedcom, name="t.ged"):
    nodes, _ = parse_nodes(gedcom)
    result = import_nodes(nodes)
    data = gedcom.encode()
    return write_import_family(result, tmp_path, data, name), result


SAMPLE = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Walt /Alder/
1 SEX M
1 BIRT
2 DATE ABT 1835
1 DEAT
2 DATE BEF 1901
1 FAMS @F1@
0 @I2@ INDI
1 NAME Ada /Alder/
1 SEX F
1 BIRT
2 DATE 2 MAR 1840
2 PLAC Leeds, England
1 OCCU Seamstress
2 DATE FROM 1862 TO 1912
1 FAMS @F1@
1 FAMS @F3@
0 @I3@ INDI
1 NAME Ben /Alder/
1 FAMC @F1@
0 @I4@ INDI
1 NAME Zed /Zorn/
1 FAMS @F3@
1 NOTE a note: with a colon
0 @I5@ INDI
1 NAME Lone /Child/
1 FAMC @F9@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 14 JUN 1862
2 PLAC Leeds, England
1 DIV
2 DATE 1870
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1875
0 @F3@ FAM
1 HUSB @I4@
1 WIFE @I2@
0 TRLR
"""


def test_import_writes_people_couples_and_refs(tmp_path):
    summary, result = import_text(tmp_path, SAMPLE)
    assert summary["people"] == 5 and summary["families"] == 3
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    tree, issues = load_tree(tmp_path)
    assert [i for i in issues if i.severity == "error"] == [], issues
    ada = tree.people["alder-ada"]
    assert ada.birth.date == "1840-03-02" and ada.birth.place == "Leeds, England"
    assert (ada.events[0].type, ada.events[0].start, ada.events[0].end) == ("occupation", "1862", "1912")
    assert tree.people["alder-walt"].birth.date == "ABT 1835" and tree.people["alder-walt"].death.date == "BEF 1901"
    assert ada.gedcom_id == "I2" and "refs: {gedcom: I2}" in text
    assert tree.people["alder-ben"].parents == ["alder-walt", "alder-ada"]
    # two FAMs for the same pair are one couple record with every event; F3 (no events) is an empty couple record
    assert text.count("alder-ada + alder-walt:") == 1 and "alder-ada + zorn-zed: {}" in text
    walt = tree.people["alder-ada"] if tree.people["alder-ada"].partnerships else tree.people["alder-walt"]
    assert [p.type for p in walt.partnerships] == ["marriage", "marriage"]
    assert walt.partnerships[0].end_reason == "divorce" and walt.partnerships[0].end == "1870"
    assert walt.partnerships[1].start == "1875" and walt.partnerships[1].end is None


def test_a_dangling_famc_and_notes_go_to_the_leftovers(tmp_path):
    summary, result = import_text(tmp_path, SAMPLE)
    assert any(i.code == "W-DANGLING-FAMC" for i in result.issues)
    extra = (tmp_path / "archive" / "gedcom-extra.yml").read_text(encoding="utf-8")
    from cronicl.core.yamltext import load_text

    loaded = load_text(extra)
    assert loaded.error is None and "1 FAMC @F9@" in loaded.data["child-lone"]
    # nothing in family.yml reads the leftovers back
    tree, _ = load_tree(tmp_path)
    assert "FAMC" not in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_the_imported_family_checks_clean_and_builds(tmp_path, capsys):
    run("init", "--dir", tmp_path)
    nodes, _ = parse_nodes(SAMPLE)
    write_import_family(import_nodes(nodes), tmp_path, SAMPLE.encode(), "t.ged")
    capsys.readouterr()
    assert run("check", "--dir", tmp_path) == 0
    assert run("build", "--dir", tmp_path, "--out", tmp_path / "out") == 0
    assert (tmp_path / "out" / "index.html").exists()
    assert (tmp_path / "archive").glob("t-*.ged")


def test_import_keeps_the_init_comments_and_refuses_a_second_import(tmp_path):
    run("init", "--dir", tmp_path)
    nodes, _ = parse_nodes(SAMPLE)
    write_import_family(import_nodes(nodes), tmp_path, SAMPLE.encode(), "t.ged")
    assert "# family.yml: the whole family" in (tmp_path / "family.yml").read_text(encoding="utf-8").split("\n\n")[0]
    with pytest.raises(ImportRefused):
        write_import_family(import_nodes(nodes), tmp_path, SAMPLE.encode(), "t.ged")


def test_import_refuses_a_split_family_folder(tmp_path):
    (tmp_path / "family").mkdir()
    nodes, _ = parse_nodes(SAMPLE)
    with pytest.raises(ImportRefused):
        write_import_family(import_nodes(nodes), tmp_path, SAMPLE.encode(), "t.ged")


def test_the_cli_imports_the_sample_into_a_new_folder(tmp_path, sample_ged, capsys):
    run("init", "--dir", tmp_path)
    capsys.readouterr()
    assert run("import-gedcom", sample_ged, "--dir", tmp_path) == 0
    assert "dry run" in capsys.readouterr().out and "alder" not in (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert run("import-gedcom", sample_ged, "--dir", tmp_path, "--apply") == 0
    tree, issues = load_tree(tmp_path)
    assert len(tree.people) == 8 and [i for i in issues if i.severity == "error"] == []
    assert tree.people["smith-bob"].birth.place == "Vancouver, BC"
    assert tree.people["jones-jane"].birth.date == "ABT 1952"
    occupation = [e for e in tree.people["smith-bob"].events if e.type == "occupation"][0]
    assert occupation.date == "BET 1975 AND 1990" and occupation.value == "Teacher"
