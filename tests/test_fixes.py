"""Warning fixes: each is a proposed edit of the file text; nothing here writes anything."""
import pytest

from cronicl.checktext import check_texts, load_tree_from_texts
from cronicl.core.fixes import fix_options
from cronicl.core.living import is_living
from datetime import date

SITE = "title: T\nschema_version: 3\n"
TODAY = date(2026, 11, 15)


def issues(text):
    return check_texts(SITE, {"family.yml": text})


def options_for(text, code):
    tree, load = load_tree_from_texts(SITE, {"family.yml": text})
    found = [i for i in check_texts(SITE, {"family.yml": text}) if i.code == code]
    assert found, (code, [i.code for i in issues(text)])
    return found[0], fix_options(tree, {"family.yml": text}, found[0])


def applied(text, option):
    return option.files["family.yml"]


@pytest.mark.parametrize(
    "text, code",
    [
        ("a:\n  name: {given: A}\n  sex:\n", "W-BLANK"),
        ("a: {name: {given: A}, sex: }\n", "W-BLANK"),
        ("c: {name: {given: C}}\nk:\n  name: {given: K}\n  parents: [c, c]\n", "W-DUPLICATE-PARENT"),
        ("a:\n  name: {given: A}\n  birht: 1900\n", "W-UNKNOWN-KEY"),
        ("a: {name: {given: A}, sex: M}\n", "W-BAD-SEX"),
        ("a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: wedding, date: 1900}\n", "W-COUPLE-EVENT-TYPE"),
    ],
)
def test_a_fix_removes_its_own_warning_and_nothing_else(text, code):
    issue, options = options_for(text, code)
    assert options, code
    before = {i.code for i in issues(text)}
    for option in options:
        after = [i for i in check_texts(SITE, option.files)]
        assert not any(i.code == code and i.line == issue.line for i in after), (option.label, [(i.code, i.line) for i in after])
        assert {i.code for i in after} <= before, option.label


def test_the_unknown_key_fix_renames_to_the_suggestion():
    text = "a:\n  name: {given: A}\n  birht: 1900\n"
    _, [option] = options_for(text, "W-UNKNOWN-KEY")
    assert applied(text, option) == "a:\n  name: {given: A}\n  birth: 1900\n"


def test_the_duplicate_parent_fix_removes_the_repeat_only():
    text = "c: {name: {given: C}}\nd: {name: {given: D}}\nk:\n  name: {given: K}\n  parents: [c, d, c]\n"
    _, [option] = options_for(text, "W-DUPLICATE-PARENT")
    assert applied(text, option).endswith("parents: [c, d]\n")


def test_bad_sex_offers_each_word_and_none_is_the_default():
    _, options = options_for("a: {name: {given: A}, sex: M}\n", "W-BAD-SEX")
    assert [o.label for o in options] == ["male", "female", "unknown", "other"] and not any(o.default for o in options)
    assert "sex: female" in applied("", options[1]) or "sex: female" in options[1].files["family.yml"]


def test_a_blank_field_fix_removes_the_line():
    text = "a:\n  name: {given: A}\n  sex:\n  bio: x\n"
    _, [option] = options_for(text, "W-BLANK")
    assert applied(text, option) == "a:\n  name: {given: A}\n  bio: x\n"


def test_the_mistyped_couple_event_is_retyped():
    text = "a: {name: {given: A}}\nb: {name: {given: B}}\na + b:\n  events:\n    - {type: wedding, date: 1900}\n"
    _, [option] = options_for(text, "W-COUPLE-EVENT-TYPE")
    assert "type: marriage" in applied(text, option)


# ---- the privacy cases ask, and the safe answer is the default
@pytest.mark.parametrize(
    "text, code",
    [
        ("a:\n  name: {given: A}\n  birth: 1990\n  death: 'no'\n", "W-DATE-UNPARSED"),
        ("a:\n  name: {given: A}\n  birth: 1990\n  death: {note: still alive}\n", "W-DEATH-EMPTY"),
        ("a:\n  name: {given: A}\n  birth: 1990\n  death: 1950\n  living: true\n", "W-LIVING-AND-DEATH"),
    ],
)
def test_a_possible_death_always_asks_and_defaults_to_alive(text, code):
    issue, options = options_for(text, code)
    assert len(options) == 2
    default = [o for o in options if o.default]
    assert len(default) == 1 and options[0] is default[0]
    tree, _ = load_tree_from_texts(SITE, default[0].files)
    assert is_living(tree.people["a"], TODAY) is True and tree.people["a"].death is None
    other = options[1]
    tree, _ = load_tree_from_texts(SITE, other.files)
    if code != "W-LIVING-AND-DEATH":
        assert is_living(tree.people["a"], TODAY) is False  # "they died": written as unknown
    else:
        assert tree.people["a"].living is None and tree.people["a"].death is not None


def test_other_warnings_have_no_automatic_fix():
    text = "a:\n  name: {given: A}\n  birth: 12 March 1900\n"
    tree, _ = load_tree_from_texts(SITE, {"family.yml": text})
    issue = [i for i in issues(text) if i.code == "W-DATE-UNPARSED"][0]
    assert fix_options(tree, {"family.yml": text}, issue) == []
