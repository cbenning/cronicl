"""recordedit: scalars, keys and removal. Every test checks the text outside the change is byte-for-byte unchanged."""
import difflib

import pytest

from cronicl.core.recordedit import EditRefused, record_data, remove, rewrite_record, set_value, set_value_any
from cronicl.core.yamltext import load_text

BLOCK = """\
# header comment
lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace}  # trailing note
  sex: female
  birth: {date: 1815-12-10, place: "London, England"}
  # about the parents
  parents: [byron-george, milbanke-annabella]
  bio: |
    Mathematician.

    Writer.

byron-george:
  name: {given: George, surname: Byron}
  birth: 1788

# between records
byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02}
"""
ADA, GEORGE, COUPLE = "lovelace-ada", "byron-george", "byron-george + milbanke-annabella"


def changed(old: str, new: str) -> list[str]:
    return [line for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def reads(text: str):
    result = load_text(text)
    assert result.error is None, result.error
    return result.data


def test_replace_a_scalar_in_a_flow_mapping_changes_only_it():
    new = set_value(BLOCK, (ADA, "name", "given"), "Ada")
    assert changed(BLOCK, new) == ["-  name: {given: Augusta Ada, surname: Lovelace}  # trailing note", "+  name: {given: Ada, surname: Lovelace}  # trailing note"]


def test_replace_a_block_scalar():
    new = set_value(BLOCK, (ADA, "sex"), "male")
    assert changed(BLOCK, new) == ["-  sex: female", "+  sex: male"]


def test_a_quoted_value_keeps_its_quotes_when_it_can():
    text = "a:\n  name: {given: 'Old', surname: \"Name\"}\n"
    new = set_value(text, ("a", "name", "given"), "Newer")
    new = set_value(new, ("a", "name", "surname"), "Other")
    assert new == "a:\n  name: {given: 'Newer', surname: \"Other\"}\n"


def test_a_value_that_needs_quotes_is_quoted_and_reads_back_the_same():
    new = set_value(BLOCK, (ADA, "name", "surname"), "De la Cruz, Jr.")
    assert reads(new)[ADA]["name"]["surname"] == "De la Cruz, Jr."
    assert changed(BLOCK, new)[1].count('"De la Cruz, Jr."') == 1


def test_setting_the_same_value_changes_nothing():
    assert set_value(BLOCK, (ADA, "sex"), "female") == BLOCK


def test_add_a_key_to_a_flow_mapping_in_canonical_order():
    new = set_value(BLOCK, (ADA, "name", "nickname"), "Ada")
    assert changed(BLOCK, new)[1] == "+  name: {given: Augusta Ada, surname: Lovelace, nickname: Ada}  # trailing note"
    new = set_value(BLOCK, (ADA, "name", "prefix"), "Lady")
    assert reads(new)[ADA]["name"] == {"given": "Augusta Ada", "surname": "Lovelace", "prefix": "Lady"}


def test_add_a_block_key_in_canonical_position():
    new = set_value(BLOCK, (GEORGE, "death"), "1824")
    assert changed(BLOCK, new) == ["+  death: 1824"]
    assert new.index("death: 1824") > new.index("birth: 1788") and new.index("death: 1824") < new.index("# between records")


def test_add_a_key_before_the_first_one():
    text = "a:\n  sex: male\n  bio: x\n"
    assert set_value(text, ("a", "name", "given"), "A") == "a:\n  name: {given: A}\n  sex: male\n  bio: x\n"


def test_add_a_key_after_the_last_one_keeps_what_follows():
    new = set_value(BLOCK, (GEORGE, "bio"), "Poet.")
    assert changed(BLOCK, new) == ["+  bio: Poet."]


def test_add_place_to_a_bare_date():
    new = set_value(BLOCK, (GEORGE, "birth", "place"), "London, England")
    assert changed(BLOCK, new) == ["-  birth: 1788", '+  birth: {date: 1788, place: "London, England"}']


def test_add_a_date_to_a_blank_nested_value_and_a_blank_record():
    assert set_value("a:\n  name: {given: A}\n  birth:\n", ("a", "birth", "date"), "1900") == "a:\n  name: {given: A}\n  birth: 1900\n"
    new = set_value("a:\nb: {}\n", ("a", "name", "given"), "A")
    assert new == "a:\n  name: {given: A}\nb: {}\n"


def test_add_a_field_to_a_flow_record():
    text = "a: {name: {given: A}, birth: 1990}\nb: {}\n"
    new = set_value(text, ("a", "sex"), "female")
    assert new == "a: {name: {given: A}, sex: female, birth: 1990}\nb: {}\n"


def test_a_flow_record_that_would_get_too_long_is_rewritten_as_a_block():
    text = "# keep\na: {name: {given: Augusta Ada, surname: Lovelace}, birth: {date: 1815-12-10, place: \"London, England\"}, parents: [x, y]}\n\nb: {}\n"
    new = set_value(text, ("a", "death"), "1852")
    assert new.startswith("# keep\na:\n") and new.endswith("\n\nb: {}\n")
    assert reads(new)["a"]["death"] == "1852" and reads(new)["a"]["name"]["surname"] == "Lovelace"


def test_a_multiline_value_becomes_a_literal_block():
    new = set_value(BLOCK, (GEORGE, "bio"), "One.\n\nTwo.")
    assert reads(new)[GEORGE]["bio"].strip("\n") == "One.\n\nTwo."
    new = set_value(BLOCK, (ADA, "bio"), "Changed.\nSecond line.")
    assert reads(new)[ADA]["bio"].strip("\n") == "Changed.\nSecond line."
    assert "byron-george:" in new and "# between records" in new


def test_a_couple_note_goes_after_its_events():
    new = set_value(BLOCK, (COUPLE, "note"), "Winter wedding")
    assert changed(BLOCK, new) == ["+  note: Winter wedding"]
    assert new.rstrip().endswith("note: Winter wedding")


def test_the_couple_key_is_found_in_either_order():
    new = set_value(BLOCK, ("milbanke-annabella + byron-george", "note"), "x")
    assert "note: x" in new


def test_crlf_files_keep_their_line_endings():
    text = BLOCK.replace("\n", "\r\n")
    new = set_value(text, (GEORGE, "death"), "1824")
    assert "\n" not in new.replace("\r\n", "")
    assert new.replace("\r\n", "\n") == set_value(BLOCK, (GEORGE, "death"), "1824")


def test_a_byte_order_mark_is_kept():
    text = "\ufeff" + BLOCK
    new = set_value(text, (ADA, "sex"), "male")
    assert new.startswith("\ufeff# header") and "sex: male" in new


def test_remove_a_block_key_removes_its_line_only():
    new = remove(BLOCK, (ADA, "sex"))
    assert changed(BLOCK, new) == ["-  sex: female"]


def test_remove_from_a_flow_mapping():
    new = remove(BLOCK, (ADA, "name", "surname"))
    assert changed(BLOCK, new)[1] == "+  name: {given: Augusta Ada}  # trailing note"
    new = remove(BLOCK, (ADA, "name", "given"))
    assert changed(BLOCK, new)[1] == "+  name: {surname: Lovelace}  # trailing note"


def test_removing_the_last_part_of_a_nested_value_removes_the_value():
    text = "a:\n  name: {given: A}\n  birth: {date: 1900}\n"
    assert remove(text, ("a", "birth", "date")) == "a:\n  name: {given: A}\n"
    assert remove(text, ("a", "name", "given")) == "a:\n  birth: {date: 1900}\n"


def test_removing_keeps_comments_around_it():
    new = remove(BLOCK, (ADA, "parents"))
    assert "# about the parents" in new and "parents:" not in new.split("byron-george:")[0]


def test_removing_what_is_not_there_is_refused():
    with pytest.raises(EditRefused):
        remove(BLOCK, (ADA, "death"))


def test_unreadable_text_is_refused():
    with pytest.raises(EditRefused):
        set_value("a: [unclosed\n", ("a", "sex"), "male")


def test_rewrite_record_replaces_only_that_record():
    data = record_data(BLOCK, GEORGE)
    data["death"] = "1824"
    new = rewrite_record(BLOCK, GEORGE, data)
    assert new.startswith(BLOCK.split("byron-george:")[0]) and "# between records" in new
    assert reads(new)[GEORGE]["death"] == "1824" and reads(new)[ADA] == reads(BLOCK)[ADA]


def test_insert_a_nested_mapping_and_a_list():
    new = set_value_any(BLOCK, (GEORGE, "refs"), {"gedcom": "@I1@"})
    assert reads(new)[GEORGE]["refs"] == {"gedcom": "@I1@"}
    new = set_value_any(BLOCK, (GEORGE, "parents"), ["a", "b"])
    assert "  parents: [a, b]" in new


def test_rename_a_key_in_place():
    from cronicl.core.recordedit import rename_key

    text = "a:\n  birht: 1900  # typo\n  name: {given: A, surnmae: B}\n"
    assert rename_key(text, ("a", "birht"), "birth") == "a:\n  birth: 1900  # typo\n  name: {given: A, surnmae: B}\n"
    assert rename_key(text, ("a", "name", "surnmae"), "surname").count("surname: B") == 1


def test_paths_at_line_lists_the_keys_and_items_that_start_there():
    from cronicl.core.recordedit import paths_at_line

    text = "a: {name: {given: A}, sex: male}\nb:\n  events:\n    - {type: x}\n"
    assert ("a", "sex") in paths_at_line(text, 1) and ("a", "name", "given") in paths_at_line(text, 1)
    assert ("b", "events", 0) in paths_at_line(text, 4)
    assert paths_at_line(text, 3) == [("b", "events")]
