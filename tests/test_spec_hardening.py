"""Rules found by the scrutiny pass over SPEC.md: each test pins one behaviour the spec states or now states."""
import datetime
from pathlib import Path

import pytest

from cronicl.core.check import check_tree
from cronicl.core.familyedit import plan_mark, plan_rename
from cronicl.core.generations import generation_conflict
from cronicl.core.living import is_living
from cronicl.core.store import load_tree
from cronicl.core.edit import EditError

TODAY = datetime.date(2026, 11, 15)


def load(tmp_path, text, files=None):
    (tmp_path / "site.yml").write_text("title: T\nschema_version: 3\n", encoding="utf-8")
    if files is None:
        (tmp_path / "family.yml").write_text(text, encoding="utf-8")
    else:
        for name, body in files.items():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    tree, issues = load_tree(tmp_path)
    return tree, check_tree(tree, issues)


def codes(issues):
    return sorted((i.code, i.line) for i in issues)


# ---- A1: a death that is not a date is no death
@pytest.mark.parametrize("value", ["~", "null", "no", "n/a", "false", "alive"])
def test_a_death_value_that_is_not_a_date_does_not_make_someone_deceased(tmp_path, value):
    tree, issues = load(tmp_path, f"a:\n  name: {{given: A}}\n  birth: 1990\n  death: '{value}'\n")
    assert is_living(tree.people["a"], TODAY) is True
    message = [i.message for i in issues if i.code == "W-DATE-UNPARSED"][0]
    assert "does not count as a death" in message


@pytest.mark.parametrize("value", ["unknown", "1950", "FROM 1950", "BEF 1950"])
def test_real_death_dates_still_count(tmp_path, value):
    tree, _ = load(tmp_path, f"a:\n  name: {{given: A}}\n  birth: 1990\n  death: '{value}'\n")
    assert is_living(tree.people["a"], TODAY) is False


def test_a_death_with_a_place_counts_but_a_bare_note_does_not(tmp_path):
    tree, _ = load(tmp_path, "a: {name: {given: A}, birth: 1990, death: {place: Leeds}}\nb: {name: {given: B}, birth: 1990, death: {note: died young}}\n")
    assert not is_living(tree.people["a"], TODAY) and is_living(tree.people["b"], TODAY)


# ---- B14: living: true next to a death is a conflict, reported
def test_living_true_with_a_death_is_reported(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: 1900\n  death: 1950\n  living: true\n")
    assert codes(issues) == [("W-LIVING-AND-DEATH", 5)]


# ---- A3: marriage 1950-06 then divorce 1950 is one ended partnership
def test_a_divorce_in_a_less_precise_date_does_not_sort_before_the_marriage(tmp_path):
    tree, _ = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: marriage, date: 1950-06}\n    - {type: divorce, date: 1950}\n")
    parts = [(p.type, p.start, p.end, p.end_reason) for p in tree.people["a"].partnerships]
    assert parts == [("marriage", "1950-06", "1950", "divorce")]


def test_a_divorce_written_first_with_the_same_date_still_follows_the_marriage(tmp_path):
    tree, _ = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: divorce, date: 1950}\n    - {type: marriage, date: 1950}\n")
    assert [(p.type, p.end_reason) for p in tree.people["a"].partnerships] == [("marriage", "divorce")]


# ---- A4: a couple's events are open
def test_any_event_type_is_allowed_in_a_couple_record(tmp_path):
    _, issues = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: residence, date: 1955, place: 'Leeds, England'}\n    - {type: census, date: 1961}\n")
    assert codes(issues) == []


def test_a_couple_event_without_a_type_is_reported(tmp_path):
    _, issues = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {date: 1955}\n")
    assert codes(issues) == [("W-EVENT-NO-TYPE", 5)]


# ---- A5: text where a list or mapping was typed is reported, not dropped
@pytest.mark.parametrize(
    "body, line",
    [
        ("  name: {given: [A, B]}\n", 2),
        ("  sex: [male]\n", 3),
        ("  portrait: {file: x.png}\n", 3),
        ("  bio: [one, two]\n", 3),
        ("  refs: {gedcom: [x]}\n", 3),
        ("  birth: {date: [1900]}\n", 3),
        ("  birth: {place: {city: Leeds}}\n", 3),
        ("  events:\n    - {type: [occupation]}\n", 4),
        ("  events:\n    - {type: occupation, value: [Teacher]}\n", 4),
        ("  living: [true]\n", 3),
    ],
)
def test_a_wrong_shaped_value_is_an_error(tmp_path, body, line):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n" + body if not body.startswith("  name:") else "a:\n" + body)
    assert [c for c, _ in codes(issues) if c == "E-RECORD-SHAPE"], codes(issues)
    assert any(c == "E-RECORD-SHAPE" and ln == line for c, ln in codes(issues)), codes(issues)


def test_cite_may_be_a_list_of_text(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: {date: 1900, cite: [one, two]}\n")
    assert codes(issues) == []


# ---- A6: files in family/ that are not read are reported
def test_family_folder_files_that_are_not_read_are_reported(tmp_path):
    tree, issues = load(tmp_path, None, files={"family/one.yml": "a: {name: {given: A}}\n", "family/two.yaml": "b: {name: {given: B}}\n", "family/sub/three.yml": "c: {name: {given: C}}\n", "family/notes.txt": "x\n"})
    assert sorted(tree.people) == ["a"]
    assert sorted(i.code for i in issues) == ["W-IGNORED-FILE", "W-IGNORED-FILE"]


def test_a_family_yaml_file_gets_a_hint(tmp_path):
    _, issues = load(tmp_path, None, files={"family.yaml": "a: {name: {given: A}}\n"})
    assert [i.code for i in issues] == ["E-NO-FAMILY"] and "family.yaml" in issues[0].message


# ---- A7: rename follows the set-aside GEDCOM lines
def test_rename_updates_the_gedcom_extra_file(tmp_path):
    load(tmp_path, "old-id: {name: {given: A}}\nb: {name: {given: B}, parents: [old-id]}\n")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "gedcom-extra.yml").write_text('old-id: |-\n  1 _UID abc\n  1 NOTE old-id here\nb: "1 _X"\n', encoding="utf-8")
    changes = {c.path.name: c.text for c in plan_rename(tmp_path, "old-id", "new-id")}
    assert changes["gedcom-extra.yml"].startswith("new-id: |-") and "NOTE old-id here" in changes["gedcom-extra.yml"]


# ---- A8: mark-deceased fills a blank death
def test_mark_deceased_fills_a_blank_death(tmp_path):
    load(tmp_path, "a:\n  name: {given: A}\n  death:\n  bio: x\n")
    [(pid, path, changed, text)] = plan_mark(tmp_path, ["a"], living=False)
    assert changed and "death: unknown" in text and "bio: x" in text


def test_mark_errors_do_not_repeat_the_person(tmp_path):
    load(tmp_path, "a: {name: {given: A}}\n")
    with pytest.raises(EditError) as err:
        plan_mark(tmp_path, ["a"], living=False)
    assert str(err.value).count("a:") == 1


# ---- A9: a repeated person key keeps one record and reports it once
def test_a_repeated_person_key_is_reported_and_the_later_record_is_used(tmp_path):
    tree, issues = load(tmp_path, "a:\n  name: {given: First}\nb: {name: {given: B}, parents: [a]}\na:\n  name: {given: Second}\n")
    assert tree.people["a"].given == "Second"
    assert codes(issues) == [("E-DUPLICATE-ID", 4)]


# ---- B13: sex words are accepted in any case
def test_sex_words_are_case_insensitive(tmp_path):
    tree, issues = load(tmp_path, "a: {name: {given: A}, sex: Female}\nb: {name: {given: B}, sex: F}\n")
    assert tree.people["a"].sex == "F" and codes(issues) == [("W-BAD-SEX", 2)]


# ---- B17: the placeholder partner the spec recommends is not a nameless person
def test_a_nameless_placeholder_partner_or_parent_is_not_reported(tmp_path):
    _, issues = load(tmp_path, "a: {name: {given: A}}\nunknown-1:\nunknown-2:\nkid: {name: {given: K}, parents: [a, unknown-2]}\na + unknown-1: {}\nloner:\n  birth: 1850\n")
    assert codes(issues) == [("W-NO-NAME", 6)]


# ---- C18: dates that cannot be right
def test_a_between_range_that_runs_backwards_is_reported(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: BET 1890 AND 1880\n")
    assert codes(issues) == [("W-END-BEFORE-START", 3)]


def test_birth_after_death_is_reported(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: 1990\n  death: 1950\n")
    assert codes(issues) == [("W-BIRTH-AFTER-DEATH", 4)]


def test_a_child_born_before_a_parent_or_long_after_their_death_is_reported(tmp_path):
    text = (
        "p: {name: {given: P}, birth: 1900, death: 1940}\n"
        "early: {name: {given: E}, birth: 1890, parents: [p]}\n"
        "late: {name: {given: L}, birth: 1943, parents: [p]}\n"
        "posthumous: {name: {given: Q}, birth: 1941, parents: [p]}\n"
        "vague: {name: {given: V}, birth: ABT 1890, parents: [p]}\n"
    )
    _, issues = load(tmp_path, text)
    assert codes(issues) == [("W-CHILD-AFTER-PARENT-DEATH", 3), ("W-CHILD-BEFORE-PARENT", 2)]


# ---- C23
def test_the_same_parent_twice_is_reported(tmp_path):
    _, issues = load(tmp_path, "c: {name: {given: C}}\nk:\n  name: {given: K}\n  parents: [c, c]\n")
    assert codes(issues) == [("W-DUPLICATE-PARENT", 4)]


# ---- A2: collateral marriages across generations draw
UNCLE_NIECE = """
gp: {name: {given: GP}}
uncle: {name: {given: U}, parents: [gp]}
sib: {name: {given: S}, parents: [gp]}
niece: {name: {given: N}, parents: [sib]}
niece + uncle:
  events: [{type: marriage, date: 1850}]
kid: {name: {given: K}, parents: [uncle, niece]}
"""


def test_an_uncle_marrying_a_niece_is_not_a_layout_conflict(tmp_path):
    tree, issues = load(tmp_path, UNCLE_NIECE)
    assert generation_conflict(tree) is None
    assert [c for c, _ in codes(issues) if c == "E-GENERATION-CONFLICT"] == []
    from cronicl.site.layout import compute_layout

    layout = compute_layout(tree)
    assert {n["id"] for n in layout["nodes"]} == {"gp", "uncle", "sib", "niece", "kid"}


def test_marrying_a_descendant_is_still_a_layout_conflict(tmp_path):
    tree, issues = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}, parents: [a]}\nc: {name: {given: C}, parents: [b]}\na + c: {}\n")
    assert generation_conflict(tree) is not None
    assert "E-GENERATION-CONFLICT" in [c for c, _ in codes(issues)]


# ================= review pass: fixes =================
import itertools
from datetime import date

from cronicl.core.familyedit import plan_mark
from cronicl.core.gedcom import import_nodes, parse_nodes
from cronicl.core.gedcom_export import export_gedcom
from cronicl.core.yamltext import load_text


def _marked(tmp_path, record):
    load(tmp_path, f"a:\n  name: {{given: A}}\n  birth: 1990\n{record}  bio: x\n")
    [(_, _, changed, text)] = plan_mark(tmp_path, ["a"], living=False)
    return changed, text


@pytest.mark.parametrize("blank", ['  death: ""\n', "  death: ''\n", "  death: !!null\n", "  death: |\n", "  death:   # unknown yet\n"])
def test_mark_deceased_fills_every_blank_form_of_death(tmp_path, blank):
    changed, text = _marked(tmp_path, blank)
    assert changed
    (tmp_path / "family.yml").write_text(text, encoding="utf-8")
    tree, issues = load_tree(tmp_path)
    assert tree.people["a"].death.date == "unknown" and is_living(tree.people["a"], TODAY) is False


@pytest.mark.parametrize("record", ["  death: no\n", "  death: {}\n", "  death: {date: no}\n", "  living: true\n"])
def test_mark_deceased_says_when_it_cannot_make_the_person_deceased(tmp_path, record):
    load(tmp_path, f"a:\n  name: {{given: A}}\n  birth: 1990\n{record}")
    with pytest.raises(EditError) as err:
        plan_mark(tmp_path, ["a"], living=False)
    assert "by hand" in str(err.value)


def test_mark_living_fills_a_quoted_blank_living(tmp_path):
    load(tmp_path, 'a:\n  name: {given: A}\n  living: ""\n  bio: x\n')
    [(_, _, changed, text)] = plan_mark(tmp_path, ["a"], living=True)
    assert changed and 'living: true' in text and '""' not in text


def _partnerships(tmp_path, events):
    body = "".join(f"    - {e}\n" for e in events)
    tree, issues = load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n" + body)
    return [(p.type, p.start, p.end, p.end_reason) for p in tree.people["a"].partnerships], issues


def test_couple_event_order_does_not_depend_on_how_they_were_written(tmp_path):
    events = ["{type: divorce, date: 1950}", "{type: marriage, date: 1950-09}", "{type: divorce, date: 1950-03}"]
    outcomes = set()
    for order in itertools.permutations(events):
        sub = tmp_path / str(len(outcomes)) / "x"
        sub.mkdir(parents=True, exist_ok=True)
        got, _ = _partnerships(sub, order)
        outcomes.add(tuple(got))
    assert len(outcomes) == 1, outcomes


def test_a_partly_dated_ending_follows_a_beginning_in_the_same_period(tmp_path):
    got, issues = _partnerships(tmp_path, ["{type: marriage, date: 1950-06}", "{type: divorce, date: 1950}"])
    assert got == [("marriage", "1950-06", "1950", "divorce")]
    assert codes(issues) == []


@pytest.mark.parametrize("kind", ["Marriage", "MARRIAGE", " marriage ", "civil union", "Civil_Union"])
def test_couple_event_types_ignore_case_and_spacing(tmp_path, kind):
    got, issues = _partnerships(tmp_path, [f"{{type: '{kind}', date: 1900}}"])
    assert got[0][0] in ("marriage", "civil-union") and got[0][1] == "1900" and codes(issues) == []


@pytest.mark.parametrize("kind, guess", [("wedding", "marriage"), ("married", "marriage"), ("divorced", "divorce"), ("marraige", "marriage"), ("separated", "separation")])
def test_a_mistyped_couple_event_type_is_reported_with_a_suggestion(tmp_path, kind, guess):
    _, issues = _partnerships(tmp_path, [f"{{type: {kind}, date: 1900}}"])
    [issue] = [i for i in issues if i.code == "W-COUPLE-EVENT-TYPE"]
    assert guess in issue.message and issue.line == 5


def test_other_couple_event_types_are_not_reported(tmp_path):
    _, issues = _partnerships(tmp_path, ["{type: residence, date: 1900}", "{type: census, date: 1911}"])
    assert codes(issues) == []


# ---- export: a couple's extra events with a source or value
def test_extra_couple_events_with_a_source_export_without_crashing(tmp_path):
    load(tmp_path, "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: census, date: 1851, value: Boarders, cite: 1851 census}\n")
    tree, _ = load_tree(tmp_path)
    text, _ = export_gedcom(tree, today=TODAY)
    assert "0 @S1@ SOUR" in text and "2 TITL 1851 census" in text.replace("1 TITL", "2 TITL") or "1 TITL 1851 census" in text
    assert "1 EVEN Boarders" in text and "2 SOUR @S1@" in text


def test_a_death_that_does_not_count_is_not_exported_as_a_death(tmp_path):
    load(tmp_path, "a:\n  name: {given: A}\n  birth: 1990\n  death: 'no'\n")
    tree, _ = load_tree(tmp_path)
    text, _ = export_gedcom(tree, today=TODAY)
    assert "DEAT" not in text


# ---- import: a DEAT with words for a date is a death
@pytest.mark.parametrize("phrase", ["Stillborn", "Deceased", "Bef. 1990", "11 FEB 1731/32"])
def test_an_imported_death_with_a_date_phrase_still_counts_as_a_death(phrase):
    nodes, _ = parse_nodes(f"0 HEAD\n0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n2 DATE {phrase}\n0 TRLR\n")
    [person] = import_nodes(nodes).people
    assert person.death is not None and person.death.date == "unknown" and phrase.replace("Bef. ", "Bef. ") in person.death.extra["note"]
    assert is_living(person, TODAY) is False


# ---- minors
def test_uppercase_yml_and_a_family_yaml_beside_family_yml_are_reported(tmp_path):
    _, issues = load(tmp_path, None, files={"family/one.yml": "a: {name: {given: A}}\n", "family/Two.YML": "b: {name: {given: B}}\n"})
    assert [i.code for i in issues] == ["W-IGNORED-FILE"]
    sub = tmp_path / "second"
    sub.mkdir()
    _, issues = load(sub, "a: {name: {given: A}}\n", files={"family.yml": "a: {name: {given: A}}\n", "family.yaml": "b: {name: {given: B}}\n"})
    assert [i.code for i in issues] == ["W-IGNORED-FILE"]


def test_a_death_mapping_with_only_a_note_does_not_count_and_is_reported(tmp_path):
    tree, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: 1990\n  death: {note: still going strong}\n")
    assert is_living(tree.people["a"], TODAY) is True
    assert codes(issues) == [("W-DEATH-EMPTY", 4)]


def test_month_precise_ranges_are_compared_by_their_bounds(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  events:\n    - {type: residence, date: FROM 1950-06 TO 1950}\n    - {type: residence, date: BET 1890-06 AND 1890-03}\n")
    assert codes(issues) == [("W-END-BEFORE-START", 5)]


def test_a_couple_that_ends_in_the_year_it_began_is_not_reported(tmp_path):
    _, issues = _partnerships(tmp_path, ["{type: marriage, date: 1950-06}", "{type: divorce, date: 1950}"])
    assert [i.code for i in issues] == []


def test_birth_after_death_compares_months_when_both_are_given(tmp_path):
    _, issues = load(tmp_path, "a:\n  name: {given: A}\n  birth: 1950-06\n  death: 1950-03\n")
    assert [c for c, _ in codes(issues)] == ["W-BIRTH-AFTER-DEATH"]


def test_rename_stops_when_the_gedcom_extra_file_cannot_be_read(tmp_path):
    load(tmp_path, "old-id: {name: {given: A}}\n")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "gedcom-extra.yml").write_text("old-id: [unclosed\n", encoding="utf-8")
    with pytest.raises(EditError) as err:
        plan_rename(tmp_path, "old-id", "new-id")
    assert "gedcom-extra.yml" in str(err.value)


def test_a_person_whose_death_is_not_a_date_is_still_redacted_in_the_site(tmp_path):
    from cronicl.site.privacy import redact

    tree, _ = load(tmp_path, "a:\n  name: {given: Real, surname: Person}\n  birth: 1990\n  death: 'no'\n")
    shown = redact(tree, mode="placeholder", today=TODAY)
    assert [p.given for p in shown.people.values()] == ["Living"]
