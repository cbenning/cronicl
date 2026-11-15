from cronicl.checktext import check_texts
from cronicl.core.issues import Issue
from cronicl.tui.recordview import build

SITE = "title: T\nschema_version: 3\n"
BLOCK = """\
# header comment
lovelace-ada:   # the countess
  name: {given: Augusta Ada, surname: Lovelace}  # trailing note
  sex: F
  birth: {date: 1815-12-10, place: "London, England"}
  # about the parents
  parents: [byron-george, milbanke-annabella]
  events:
    - {type: occupation, value: Mathematician}
    - type: residence
      date: FROM 1835 TO 1852
  bio: |
    Mathematician.

byron-george: {name: {given: George}, birth: 1788}
milbanke-annabella:
"""


def view(key="lovelace-ada", text=BLOCK):
    issues = check_texts(SITE, {"family.yml": text})
    return build(text, key, issues, lambda pid: {"byron-george": "George Byron"}.get(pid, ""))


def rows_of(v):
    return [(r.depth, r.label, r.value) for r in v.rows if not r.comment_only]


def test_a_record_becomes_one_row_per_leaf():
    assert rows_of(view())[:9] == [
        (0, "name", ""), (1, "given", "Augusta Ada"), (1, "surname", "Lovelace"), (0, "sex", "F"),
        (0, "birth", ""), (1, "date", "1815-12-10"), (1, "place", "London, England"),
        (0, "parents", ""), (1, "-", "byron-george"),
    ]


def test_events_show_each_item_with_its_fields():
    rows = rows_of(view())
    assert (0, "events", "") in rows and (1, "-", "event 1") in rows and (2, "type", "occupation") in rows and (2, "value", "Mathematician") in rows
    assert (1, "-", "event 2") in rows and (2, "date", "FROM 1835 TO 1852") in rows


def test_a_bare_date_stays_one_row_and_bio_shows_its_text():
    v = view(key="byron-george")
    assert (0, "birth", "1788") in rows_of(v)
    assert any(r.label == "bio" and "Mathematician." in r.value for r in view().rows)


def test_comments_are_kept_and_shown():
    v = view()
    comments = [r.value for r in v.rows if r.comment_only]
    assert "about the parents" in comments[0] or any("about the parents" in c for c in comments)
    name_row = next(r for r in v.rows if r.label == "name")
    assert name_row.comment == "trailing note"


def test_paths_and_lines_point_into_the_file():
    v = view()
    given = next(r for r in v.rows if r.label == "given")
    assert given.path == ("lovelace-ada", "name", "given") and given.line == 3
    typed = next(r for r in v.rows if r.label == "type" and r.value == "residence")
    assert typed.path == ("lovelace-ada", "events", 1, "type")


def test_a_check_issue_marks_the_row_it_points_at():
    v = view()
    sex = next(r for r in v.rows if r.label == "sex")
    assert [i.code for i in sex.problems] == ["W-BAD-SEX"]
    assert not next(r for r in v.rows if r.label == "given").problems


def test_parents_carry_the_name_of_the_person():
    row = next(r for r in view().rows if r.label == "-" and r.value == "byron-george")
    assert row.extra == "George Byron"


def test_a_blank_record_has_no_rows_and_a_couple_record_works():
    assert view(key="milbanke-annabella").rows == []
    text = "a: {}\nb: {}\na + b:\n  events:\n    - {type: marriage, date: 1900}\n"
    v = build(text, "a + b", [], lambda pid: "")
    assert (1, "type", "marriage") in [(r.depth, r.label, r.value) for r in v.rows] or (2, "type", "marriage") in rows_of(v)
