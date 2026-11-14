import pytest

from cronicl.core.relations import build_relations
from cronicl.core.store import load_tree

EXAMPLE = """\
# ---- Byron line ----

byron-george:
  name: {given: George, surname: Byron}
  birth: {date: 1788-01-22, place: "London, England"}
  death: {date: 1824-04-19, place: "Missolonghi, Greece"}

milbanke-annabella:
  name: {given: Annabella, surname: Milbanke}
  birth: 1792-05-17

byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02, place: "Seaham, England"}
    - {type: separation, date: 1816}

lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace, nickname: Ada, also: [Countess of Lovelace, A. A. King]}
  sex: female
  birth:
    date: 1815-12-10
    place: London, England
    note: Born at Piccadilly Terrace.
    cite: Parish register, St George Hanover Square
  death: {date: 1852-11-27, place: "London, England"}
  parents: [byron-george, milbanke-annabella]
  events:
    - {type: occupation, value: Mathematician, cite: Letters to Charles Babbage}
    - {type: residence, date: FROM 1835 TO 1852, place: "Ockham Park, Surrey"}
    - {type: burial, date: 1852-12-03, place: "Hucknall, Nottinghamshire"}
  portrait: ada.png
  refs: {gedcom: "@I123@", gallery: ada-lovelace}
  x-nickname: Enchantress of Number
  bio: |
    Mathematician and writer.

    She is often described as the first computer programmer.

king-william + lovelace-ada:
  events:
    - {type: marriage, date: 1835-07-08, place: "Ockham, Surrey"}
"""


def load(tmp_path, write_family, text):
    write_family(tmp_path, text)
    tree, issues = load_tree(tmp_path)
    return tree, issues


def codes(issues):
    return sorted(i.code for i in issues if i.code != "W-NO-SITE-YML")


def test_the_example_loads_into_the_model(tmp_path, write_family):
    tree, issues = load(tmp_path, write_family, EXAMPLE + "\nking-william:\n  name: {given: William, surname: King}\n")
    assert [i for i in issues if i.severity == "error"] == []
    ada = tree.people["lovelace-ada"]
    assert (ada.given, ada.surname, ada.nickname, ada.also) == ("Augusta Ada", "Lovelace", "Ada", ["Countess of Lovelace", "A. A. King"])
    assert ada.sex == "F" and ada.birth.date == "1815-12-10" and ada.birth.place == "London, England"
    assert ada.birth.extra == {"note": "Born at Piccadilly Terrace.", "cite": "Parish register, St George Hanover Square"}
    assert ada.death.date == "1852-11-27" and ada.parents == ["byron-george", "milbanke-annabella"]
    assert [e.type for e in ada.events] == ["occupation", "residence", "burial"]
    assert ada.events[0].value == "Mathematician" and ada.events[0].cite == ["Letters to Charles Babbage"]
    assert (ada.events[1].date, ada.events[1].start, ada.events[1].end) == (None, "1835", "1852")
    assert ada.portrait == "ada.png" and ada.gedcom_id == "@I123@" and ada.gallery_id == "ada-lovelace"
    assert ada.extra == {"x-nickname": "Enchantress of Number"}
    assert ada.body.startswith("Mathematician and writer.") and "first computer programmer" in ada.body
    assert (ada.source, ada.line) == ("family.yml", 17)
    assert tree.people["byron-george"].birth.place == "London, England"
    assert tree.people["milbanke-annabella"].birth.date == "1792-05-17"


def test_couple_events_become_partnerships_on_the_first_sorting_partner(tmp_path, write_family):
    tree, issues = load(tmp_path, write_family, EXAMPLE + "\nking-william:\n  name: {given: William, surname: King}\n")
    byron = tree.people["byron-george"]
    assert [(p.with_id, p.type, p.start, p.end, p.end_reason) for p in byron.partnerships] == [
        ("milbanke-annabella", "marriage", "1815-01-02", "1816", "separation")
    ]
    assert byron.partnerships[0].place == "Seaham, England"
    king = tree.people["king-william"]
    assert [(p.with_id, p.type, p.start, p.end) for p in king.partnerships] == [("lovelace-ada", "marriage", "1835-07-08", None)]
    assert tree.people["lovelace-ada"].partnerships == [] and tree.people["milbanke-annabella"].partnerships == []


def test_ended_and_remarried_couples(tmp_path, write_family):
    text = """\
a:
  name: {given: A}
b:
  name: {given: B}
a + b:
  events:
    - {type: marriage, date: 1900}
    - {type: divorce, date: 1910}
    - {type: marriage, date: 1920}
c:
  name: {given: C}
d:
  name: {given: D}
c + d:
  events:
    - {type: marriage, date: 1900}
    - {type: end, date: 1910}
e:
  name: {given: E}
f:
  name: {given: F}
e + f:
  events:
    - {type: annulment, date: 1950}
g:
  name: {given: G}
h:
  name: {given: H}
g + h: {}
"""
    tree, issues = load(tmp_path, write_family, text)
    assert codes(issues) == []
    rel = build_relations(tree)
    assert not rel.couples["a+b"].ended and len(rel.couples["a+b"].partnerships) == 2
    assert rel.couples["c+d"].ended and rel.couples["c+d"].partnerships[0].end_reason is None
    assert rel.couples["e+f"].ended and rel.couples["e+f"].partnerships[0].start is None
    assert "h" in tree.people["g"].spouse and "g+h" in rel.couples and not rel.couples["g+h"].ended


def test_events_are_ordered_by_date_and_undated_ones_keep_their_place(tmp_path, write_family):
    text = "a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  events:\n    - {type: divorce, date: 1910}\n    - {type: marriage, date: 1900}\n"
    tree, _ = load(tmp_path, write_family, text)
    (p,) = tree.people["a"].partnerships
    assert (p.start, p.end, p.end_reason) == ("1900", "1910", "divorce")


def test_a_couple_note_survives(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family, "a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  note: Together since school.\n")
    (p,) = tree.people["a"].partnerships
    assert p.note == "Together since school." and p.type is None


def test_the_result_matches_an_equivalent_hand_built_tree(tmp_path, write_family, make_tree):
    from cronicl.core.model import Partnership

    tree, _ = load(tmp_path, write_family, "a:\n  name: {given: A}\nb:\n  name: {given: B}\nc:\n  name: {given: C}\n  parents: [a, b]\na + b:\n  events:\n    - {type: marriage, date: 1900}\n")
    built = make_tree(
        [
            {"id": "a", "given": "A", "partnerships": [Partnership("b", type="marriage", start="1900")]},
            {"id": "b", "given": "B"},
            {"id": "c", "given": "C", "parents": ["a", "b"]},
        ]
    )
    mine, theirs = build_relations(tree), build_relations(built)
    assert (mine.couples.keys(), mine.kids, mine.parents) == (theirs.couples.keys(), theirs.kids, theirs.parents)
    assert [vars(p) for p in mine.couples["a+b"].partnerships] == [vars(p) for p in theirs.couples["a+b"].partnerships]


@pytest.mark.parametrize(
    "text, code, line",
    [
        ("Not A Key:\n  name: {given: X}\n", "E-RECORD-KEY", 1),
        ("a + b + c:\n  events: []\n", "E-RECORD-KEY", 1),
        ("a + a:\n  events: []\n", "E-COUPLE-SELF", 1),
        ("a:\n  name: {given: A}\na:\n  name: {given: B}\n", "E-DUPLICATE-ID", 3),
        ("a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b: {}\nb + a: {}\n", "E-DUPLICATE-ID", 6),
        ("a: just text\n", "E-RECORD-SHAPE", 1),
        ("a:\n  name: Plain Text\n", "E-RECORD-SHAPE", 2),
        ("a:\n  name: {given: A}\n  parents: smith\n", "E-RECORD-SHAPE", 3),
        ("a:\n  name: {given: A}\n  events: hello\n", "E-RECORD-SHAPE", 3),
        ("a:\n  name: {given: A}\n  events: [hello]\n", "E-RECORD-SHAPE", 3),
        ("a:\n  name: {given: A}\n  birth: [1, 2]\n", "E-RECORD-SHAPE", 3),
        ("a:\n  name: {given: A}\na + ghost: {}\n", "E-DANGLING-REF", 3),
        ("a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  events:\n    - {type: wedding, date: 1900}\n", "W-COUPLE-EVENT", 7),
    ],
)
def test_record_problems_are_reported_with_their_line(tmp_path, write_family, text, code, line):
    tree, issues = load(tmp_path, write_family, text)
    found = [(i.code, i.path, i.line) for i in issues if i.code == code]
    assert (code, "family.yml", line) in found, [(i.code, i.line) for i in issues]


def test_a_bad_record_is_skipped_but_the_rest_loads(tmp_path, write_family):
    tree, issues = load(tmp_path, write_family, "a: just text\nb:\n  name: {given: B}\n")
    assert list(tree.people) == ["b"]


def test_a_syntax_error_gives_no_records_and_a_line(tmp_path, write_family):
    tree, issues = load(tmp_path, write_family, "a:\n\tname: A\n")
    (issue,) = [i for i in issues if i.code == "E-BAD-FAMILY"]
    assert tree.people == {} and issue.line == 2 and issue.path == "family.yml"


def test_merge_keys_and_non_mapping_files_are_errors(tmp_path, write_family):
    _, issues = load(tmp_path, write_family, "base: &b\n  name: {given: X}\na:\n  <<: *b\n")
    assert "E-BAD-FAMILY" in codes(issues)
    _, issues = load(tmp_path / "two", write_family, "- a\n- b\n")
    assert "E-BAD-FAMILY" in codes(issues)


def test_a_blank_record_is_an_empty_person(tmp_path, write_family):
    tree, issues = load(tmp_path, write_family, "a:\n")
    assert "a" in tree.people and [i.code for i in issues if i.severity == "error"] == []


def test_split_family_folder(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n", "family/one.yml")
    write_family(tmp_path, "b:\n  name: {given: B}\n  parents: [a]\na + c: {}\nc:\n  name: {given: C}\n", "family/two.yml")
    tree, issues = load_tree(tmp_path)
    assert sorted(tree.people) == ["a", "b", "c"] and tree.people["b"].source == "family/two.yml"
    assert [i for i in issues if i.severity == "error"] == []


def test_the_same_person_in_two_split_files_is_a_duplicate(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n", "family/one.yml")
    write_family(tmp_path, "a:\n  name: {given: A again}\n", "family/two.yml")
    _, issues = load_tree(tmp_path)
    (dup,) = [i for i in issues if i.code == "E-DUPLICATE-ID"]
    assert dup.path == "family/two.yml" and dup.line == 1


def test_both_family_yml_and_a_family_folder_is_an_error(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n")
    write_family(tmp_path, "b:\n  name: {given: B}\n", "family/x.yml")
    _, issues = load_tree(tmp_path)
    assert "E-BAD-FAMILY" in codes(issues)


def test_an_old_layout_folder_says_to_migrate(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\n---\n")
    tree, issues = load_tree(tmp_path)
    assert not tree.people
    (missing,) = [i for i in issues if i.code == "E-NO-FAMILY"]
    assert "cronicl migrate" in missing.message


def test_the_comma_trap_loads_without_crashing(tmp_path, write_family):
    tree, _ = load(tmp_path, write_family, "a:\n  name: {given: A}\n  birth: {date: 1850, place: London, England}\n")
    assert tree.people["a"].birth.place == "London"


def test_issue_to_dict_and_text_include_the_line():
    from cronicl.core.issues import Issue

    issue = Issue("W-X", "msg", "family.yml", 7)
    assert issue.to_dict()["line"] == 7 and Issue("W-X", "m").to_dict()["line"] is None
