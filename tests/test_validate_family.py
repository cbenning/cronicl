import pytest

from cronicl.checks import check_all
from cronicl.core.store import load_tree

BASE = "a:\n  name: {given: A}\nb:\n  name: {given: B}\n"


def run(tmp_path, write_family, text):
    write_family(tmp_path, text)
    tree, load = load_tree(tmp_path)
    return check_all(tree, load)


def found(issues, code):
    return sorted((i.path, i.line) for i in issues if i.code == code)


CASES = [
    # code, family text, expected line(s)
    ("W-UNKNOWN-KEY", "a:\n  name: {given: A}\n  birht: 1850\n", [3]),
    ("W-UNKNOWN-KEY", "a:\n  name: {given: A, maiden: X}\n", [2]),
    ("W-UNKNOWN-KEY", "a:\n  name: {given: A}\n  birth:\n    date: 1850\n    palce: X\n", [5]),
    ("W-UNKNOWN-KEY", "a:\n  name: {given: A}\n  events:\n    - {type: job}\n    - {type: job, colour: red}\n", [5]),
    ("W-UNKNOWN-KEY", "a:\n  name: {given: A}\n  refs: {gedcom: x, flickr: y}\n", [3]),
    ("W-UNKNOWN-KEY", BASE + "a + b:\n  colour: red\n", [6]),
    ("W-BLANK", "a:\n  name: {given: A}\n  death:\n", [3]),
    ("W-BLANK", "a:\n  name: {given: A}\n  birth: {date: 1850, place: }\n", [3]),
    ("W-FLOW-COMMA", "a:\n  name: {given: A}\n  birth: {date: 1850, place: London, England}\n", [3]),
    ("W-DATE-UNPARSED", "a:\n  name: {given: A}\n  birth: 19x0\n", [3]),
    ("W-DATE-UNPARSED", "a:\n  name: {given: A}\n  events:\n    - {type: job, date: whenever}\n", [4]),
    ("W-DATE-UNPARSED", BASE + "a + b:\n  events:\n    - {type: marriage, date: nonsense}\n", [7]),
    ("W-DATE-SPAN", "a:\n  name: {given: A}\n  birth: {date: FROM 1900 TO 1910}\n", [3]),
    ("W-DATE-SPAN", BASE + "a + b:\n  events:\n    - {type: marriage, date: FROM 1900 TO 1910}\n", [7]),
    ("W-BAD-SEX", "a:\n  name: {given: A}\n  sex: F\n", [3]),
    ("W-BAD-SEX", "a:\n  name: {given: A}\n  sex: woman\n", [3]),
    ("W-LIVING-FALSE", "a:\n  name: {given: A}\n  living: false\n", [3]),
    ("W-LIVING-FALSE", "a:\n  name: {given: A}\n  living: maybe\n", [3]),
    ("W-EVENT-IS-FIELD", "a:\n  name: {given: A}\n  events:\n    - {type: birth, date: 1850}\n", [4]),
    ("W-EVENT-ONCE", "a:\n  name: {given: A}\n  events:\n    - {type: burial, date: 1900}\n    - {type: burial, date: 1901}\n", [5]),
    ("W-EVENT-PLACEMENT", "a:\n  name: {given: A}\n  events:\n    - {type: marriage, date: 1900}\n", [4]),
    ("W-NO-NAME", "a:\n  birth: 1850\n", [1]),
    ("E-DANGLING-REF", "a:\n  name: {given: A}\n  parents: [ghost]\n", [3]),
    ("E-CYCLE", "a:\n  name: {given: A}\n  parents: [b]\nb:\n  name: {given: B}\n  parents: [a]\n", [1]),
    ("W-DUPLICATE-KEY", "a:\n  name: {given: A}\n  birth: 1850\n  birth: 1860\n", [4]),
    ("E-RECORD-KEY", "Not A Key:\n  name: X\n", [1]),
    ("E-BAD-FAMILY", "a:\n\tname: A\n", [2]),
]


@pytest.mark.parametrize("code, text, lines", CASES, ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(CASES)])
def test_each_rule_reports_its_line(tmp_path, write_family, code, text, lines):
    issues = run(tmp_path, write_family, text)
    assert [line for path, line in found(issues, code)] == lines, [(i.code, i.line) for i in issues]
    assert all(path == "family.yml" for path, _ in found(issues, code))


CLEAN = """\
alder-ada:
  name: {given: Ada, surname: Alder, nickname: Addie, also: [Ada King]}
  sex: female
  birth: {date: ABT 1850, place: "Leeds, England", note: n, cite: [c1, c2]}
  death: unknown
  events:
    - {type: occupation, value: Seamstress}
    - {type: residence, date: FROM 1862 TO 1912, place: Leeds}
    - {type: burial, date: BET 1912-11 AND 1912-12}
  refs: {gedcom: "@I1@"}
  x-nickname: Addie
  bio: |
    Words.
alder-walter:
  name: {given: Walter, surname: Alder}
  birth: 1835
alder-ada + alder-walter:
  events:
    - {type: marriage, date: 1862-06-14, place: Leeds, note: St Peter's, cite: Register}
    - {type: divorce, date: unknown}
  note: Together long.
  x-source: grandma
"""


def test_a_clean_file_has_no_issues(tmp_path, write_family):
    issues = run(tmp_path, write_family, CLEAN)
    assert [(i.code, i.line) for i in issues] == []


def test_an_unknown_key_with_a_close_match_suggests_it(tmp_path, write_family):
    (i,) = [x for x in run(tmp_path, write_family, "a:\n  name: {given: A}\n  birht: 1850\n") if x.code == "W-UNKNOWN-KEY"]
    assert "'birht'" in i.message and "did you mean 'birth'?" in i.message


def test_the_comma_trap_has_its_own_hint_and_no_unknown_key_warning(tmp_path, write_family):
    issues = run(tmp_path, write_family, "a:\n  name: {given: A}\n  birth: {date: 1850, place: London, England}\n")
    (i,) = [x for x in issues if x.code == "W-FLOW-COMMA"]
    assert "quote" in i.message and "England" in i.message
    assert not [x for x in issues if x.code == "W-UNKNOWN-KEY"]


def test_death_unknown_and_dates_unknown_are_fine(tmp_path, write_family):
    issues = run(tmp_path, write_family, BASE.replace("{given: B}", "{given: B}\n  death: unknown") + "a + b:\n  events:\n    - {type: divorce, date: unknown}\n")
    assert [i.code for i in issues] == []


def test_x_keys_are_silent_everywhere(tmp_path, write_family):
    text = "a:\n  name: {given: A, x-pet: cat}\n  x-top: 1\n  birth: {date: 1850, x-src: gran}\n  events:\n    - {type: job, x-boss: z}\n  refs: {x-other: 1}\n"
    assert [i.code for i in run(tmp_path, write_family, text)] == []


def test_end_before_start_in_an_event_span(tmp_path, write_family):
    issues = run(tmp_path, write_family, "a:\n  name: {given: A}\n  events:\n    - {type: residence, date: FROM 1950 TO 1900}\n")
    assert found(issues, "W-END-BEFORE-START") == [("family.yml", 4)]


def test_text_output_and_json_include_the_line(tmp_path, write_family, capsys):
    from cronicl.cli import main

    write_family(tmp_path, "a:\n  name: {given: A}\n  birht: 1850\n")
    main(["check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "family.yml:3" in out and "W-UNKNOWN-KEY" in out
    main(["check", "--dir", str(tmp_path), "--format", "json"])
    import json

    assert any(item["line"] == 3 and item["code"] == "W-UNKNOWN-KEY" for item in json.loads(capsys.readouterr().out))


def test_a_portrait_is_checked_against_media_next_to_family_yml(tmp_path, write_family):
    issues = run(tmp_path, write_family, "a:\n  name: {given: A}\n  portrait: missing.png\n")
    assert found(issues, "W-PORTRAIT-MISSING") == [("family.yml", 1)] or found(issues, "W-PORTRAIT-MISSING") == [("family.yml", 3)]
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "ok.png").write_bytes(b"x")
    assert "W-PORTRAIT-MISSING" not in [i.code for i in run(tmp_path, write_family, "a:\n  name: {given: A}\n  portrait: ok.png\n")]
