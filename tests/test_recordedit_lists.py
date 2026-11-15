"""recordedit: lists, couples and whole records."""
import difflib

import pytest

from cronicl.core.recordedit import (
    EditRefused,
    add_couple_event,
    add_couple_record,
    add_person_record,
    couple_key,
    list_add,
    list_remove,
    list_replace,
    record_text,
    replace_record,
)
from cronicl.core.yamltext import load_text

FAMILY = """\
# the Byrons
byron-george:
  name: {given: George, surname: Byron}
  parents: [a-parent]
  events:
    - {type: occupation, value: Poet}
    - {type: residence, date: 1815, place: "London, England"}

milbanke-annabella:
  name: {given: Annabella, surname: Milbanke}
  parents:
    - first-parent
    - second-parent

# the child
lovelace-ada:
  name: {given: Ada, surname: Lovelace}
"""
GEORGE, ANNABELLA, ADA = "byron-george", "milbanke-annabella", "lovelace-ada"


def changed(old, new):
    return [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]


def reads(text):
    result = load_text(text)
    assert result.error is None, result.error
    return result.data


def test_add_a_parent_to_a_flow_list():
    new = list_add(FAMILY, (GEORGE, "parents"), "b-parent")
    assert changed(FAMILY, new) == ["-  parents: [a-parent]", "+  parents: [a-parent, b-parent]"]


def test_add_a_parent_to_a_block_list():
    new = list_add(FAMILY, (ANNABELLA, "parents"), "third")
    assert changed(FAMILY, new) == ["+    - third"]
    assert list(reads(new)[ANNABELLA]["parents"]) == ["first-parent", "second-parent", "third"]


def test_add_to_an_empty_flow_list():
    assert list_add("a:\n  parents: []\n", ("a", "parents"), "p") == "a:\n  parents: [p]\n"


def test_a_missing_parents_list_is_created_in_place():
    new = list_add(FAMILY, (ADA, "parents"), "byron-george")
    assert changed(FAMILY, new) == ["+  parents: [byron-george]"]
    assert new.index("parents: [byron-george]") > new.index("name: {given: Ada")


def test_add_an_event_to_a_block_list():
    new = list_add(FAMILY, (GEORGE, "events"), {"type": "burial", "date": "1824-04-19", "place": "Hucknall, Nottinghamshire"})
    assert changed(FAMILY, new) == ['+    - {type: burial, date: 1824-04-19, place: "Hucknall, Nottinghamshire"}']
    assert len(reads(new)[GEORGE]["events"]) == 3


def test_a_missing_events_list_is_created():
    new = list_add(FAMILY, (ADA, "events"), {"type": "occupation", "value": "Mathematician"})
    assert reads(new)[ADA]["events"][0]["value"] == "Mathematician"
    assert "events:\n    - {type: occupation, value: Mathematician}" in new


def test_add_an_event_to_a_flow_list():
    text = "a:\n  events: [{type: x}]\n"
    new = list_add(text, ("a", "events"), {"type": "y"})
    assert reads(new)["a"]["events"][1]["type"] == "y" and new.startswith("a:\n  events: [{type: x}, {type: y}]")


def test_remove_list_items():
    new = list_remove(FAMILY, (ANNABELLA, "parents"), 0)
    assert changed(FAMILY, new) == ["-    - first-parent"]
    new = list_remove(FAMILY, (GEORGE, "events"), 1)
    assert changed(FAMILY, new) == ['-    - {type: residence, date: 1815, place: "London, England"}']
    new = list_remove(FAMILY, (GEORGE, "parents"), 0)  # the last item takes the key with it
    assert "parents" not in new.split("milbanke")[0]


def test_replace_an_event_item():
    new = list_replace(FAMILY, (GEORGE, "events"), 1, {"type": "residence", "date": "1816", "place": "Venice, Italy"})
    assert changed(FAMILY, new) == ['-    - {type: residence, date: 1815, place: "London, England"}', '+    - {type: residence, date: 1816, place: "Venice, Italy"}']


def test_replace_a_scalar_item():
    assert list_replace(FAMILY, (ANNABELLA, "parents"), 1, "other").count("other") == 1


def test_add_a_person_record_at_the_end_with_a_blank_line():
    new = add_person_record(FAMILY, "new-person", {"name": {"given": "New", "surname": "Person"}, "sex": "female", "parents": [ADA]})
    assert new.startswith(FAMILY) and new.endswith("\nnew-person:\n  name: {given: New, surname: Person}\n  sex: female\n  parents: [lovelace-ada]\n")
    assert new[len(FAMILY)] == "\n"


def test_add_a_person_record_to_a_file_without_a_final_newline_and_with_crlf():
    text = "a:\r\n  name: {given: A}"
    new = add_person_record(text, "b", {"name": {"given": "B"}})
    assert new == "a:\r\n  name: {given: A}\r\n\r\nb:\r\n  name: {given: B}\r\n"


def test_add_to_an_empty_file():
    assert add_person_record("", "a", {"name": {"given": "A"}}) == "a:\n  name: {given: A}\n"


def test_couple_key_sorts_the_pair():
    assert couple_key("b", "a") == "a + b"


def test_a_couple_goes_directly_after_its_second_partner():
    new = add_couple_record(FAMILY, GEORGE, ADA, [{"type": "marriage", "date": "1835"}])
    key = couple_key(GEORGE, ADA)
    assert key == "byron-george + lovelace-ada"
    assert new.rstrip().endswith("events:\n    - {type: marriage, date: 1835}")  # Ada's record is last, so the couple is last
    assert changed(FAMILY, new)[0].startswith("+") and new.index(key) > new.index("lovelace-ada:")
    second = add_couple_record(FAMILY, GEORGE, ANNABELLA, [{"type": "marriage", "date": "1815"}])
    assert second.index("byron-george + milbanke-annabella") > second.index("milbanke-annabella:\n") and second.index("byron-george + milbanke") < second.index("# the child")


def test_a_couple_whose_partner_is_in_another_file_goes_at_the_end():
    new = add_couple_record("a:\n  name: {given: A}\n", "a", "elsewhere", [])
    assert new.endswith("\na + elsewhere: {}\n")


def test_adding_an_existing_couple_is_refused():
    text = FAMILY + "\nbyron-george + lovelace-ada: {}\n"
    with pytest.raises(EditRefused):
        add_couple_record(text, ADA, GEORGE, [])


def test_add_a_couple_event_to_an_existing_couple_in_either_order():
    text = FAMILY + "\nlovelace-ada + byron-george:\n  events:\n    - {type: marriage, date: 1835}\n"
    new = add_couple_event(text, GEORGE, ADA, {"type": "residence", "date": "1840"})
    data = reads(new)
    assert [k for k in data if "+" in k] == ["lovelace-ada + byron-george"]
    assert [e["type"] for e in data["lovelace-ada + byron-george"]["events"]] == ["marriage", "residence"]


def test_add_a_couple_event_creates_the_couple():
    new = add_couple_event(FAMILY, GEORGE, ANNABELLA, {"type": "marriage", "date": "1815-01-02", "place": "Seaham, England"})
    assert reads(new)["byron-george + milbanke-annabella"]["events"][0]["place"] == "Seaham, England"


def test_record_text_is_the_records_own_lines():
    assert record_text(FAMILY, ANNABELLA) == "milbanke-annabella:\n  name: {given: Annabella, surname: Milbanke}\n  parents:\n    - first-parent\n    - second-parent\n"


def test_replace_a_record_by_its_raw_text():
    raw = "milbanke-annabella:\n  name: {given: Anne, surname: Milbanke}\n"
    new = replace_record(FAMILY, ANNABELLA, raw)
    assert new.startswith("# the Byrons") and "# the child" in new and "given: Anne" in new and "first-parent" not in new


def test_replace_record_refuses_a_changed_key_or_broken_yaml():
    with pytest.raises(EditRefused):
        replace_record(FAMILY, ANNABELLA, "someone-else:\n  name: {given: X}\n")
    with pytest.raises(EditRefused):
        replace_record(FAMILY, ANNABELLA, "milbanke-annabella:\n  name: [unclosed\n")
    with pytest.raises(EditRefused):
        replace_record(FAMILY, ANNABELLA, "milbanke-annabella: {}\nextra: {}\n")


def test_replace_record_keeps_the_files_line_endings():
    text = FAMILY.replace("\n", "\r\n")
    new = replace_record(text, ANNABELLA, "milbanke-annabella:\n  sex: female\n")
    assert "\n" not in new.replace("\r\n", "")


def test_an_event_goes_into_an_empty_couple_record():
    text = "a:\n  name: {given: A}\n\nb:\n  name: {given: B}\n\na + b: {}\n"
    new = add_couple_event(text, "b", "a", {"type": "marriage", "date": "1900"})
    assert new == text.replace("a + b: {}", "a + b: {events: [{type: marriage, date: 1900}]}")


def test_a_flow_list_that_would_grow_too_long_is_rewritten():
    long_name = "x" * 60
    text = f"a:\n  parents: [{long_name}-1, {long_name}-2]\n\nb: {{}}\n"
    new = list_add(text, ("a", "parents"), "p")
    assert reads(new)["a"]["parents"][-1] == "p" and new.endswith("\nb: {}\n")
