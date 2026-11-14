import time

import pytest

from cronicl.core.yamltext import Mapping, Sequence, load_text, locate


def test_key_lines_top_level_and_nested():
    result = load_text("a:\n  b: 1\n  c: 2\nd: 3\n")
    assert isinstance(result.data, Mapping)
    assert result.data.lines == {"a": 1, "d": 4}
    assert result.data["a"].lines == {"b": 2, "c": 3}
    assert result.data.line == 1 and result.data["a"].line == 2


def test_sequences_know_their_item_lines():
    result = load_text("p: [x, y]\nq:\n  - m\n  - n\n")
    assert isinstance(result.data["p"], Sequence)
    assert result.data["p"].lines == [1, 1] and result.data["q"].lines == [3, 4]


@pytest.mark.parametrize("word", ["NO", "1066", "0123", "yes", "~", "null", "true", "1e3", "2020-01-01", "0x1F"])
def test_every_scalar_stays_text(word):
    assert load_text(f"k: {word}\n").data == {"k": word}


def test_blank_values_are_empty_text_and_quotes_work():
    assert load_text('a:\nb: ""\nc: "x: y"\nd: \'it\'\'s\'\n').data == {"a": "", "b": "", "c": "x: y", "d": "it's"}


def test_duplicates_are_reported_with_the_later_line_at_any_depth():
    result = load_text("a: 1\nb:\n  c: 1\n  c: 2\na: 3\n")
    assert result.error is None and result.data["a"] == "3" and result.data["b"]["c"] == "2"
    assert sorted(result.duplicates) == [("a", 5), ("c", 4)]


def test_merge_keys_are_reported():
    result = load_text("base: &b\n  x: 1\nother:\n  <<: *b\n")
    assert result.merge_keys == [4]


def test_aliases_expand_to_the_same_text():
    assert load_text("a: &x hello\nb: *x\n").data == {"a": "hello", "b": "hello"}


@pytest.mark.parametrize("raw", ["[a]: x\n", "? [a, b]\n: y\n", "{a: b}: c\n"])
def test_a_collection_used_as_a_key_is_an_error_with_a_line(raw):
    result = load_text(raw)
    assert result.error and "key" in result.error.lower() and result.error_line == raw.count("\n", 0, 0) + 1


def test_tabs_are_an_error_with_a_line():
    result = load_text("a:\n\tb: 1\n")
    assert result.error and result.error_line == 2


def test_crlf_and_bom_give_the_same_lines():
    lf = load_text("a: 1\nb:\n  c: 2\n").data
    crlf = load_text("\ufeffa: 1\r\nb:\r\n  c: 2\r\n").data
    assert crlf.lines == lf.lines and crlf["b"].lines == lf["b"].lines


def test_flow_mappings_get_lines_and_the_comma_trap_parses():
    result = load_text("rec:\n  birth: {date: 1850, place: London, England}\n")
    flow = result.data["rec"]["birth"]
    assert flow == {"date": "1850", "place": "London", "England": ""}
    assert flow.lines["England"] == 2


def test_non_string_keys_are_kept_as_text():
    assert load_text("1: a\n2020-01-01: b\n").data == {"1": "a", "2020-01-01": "b"}


@pytest.mark.parametrize("raw", ["", "# only a comment\n", "---\n", "\n\n"])
def test_an_empty_document_is_an_empty_mapping(raw):
    result = load_text(raw)
    assert result.error is None and result.data == {} and isinstance(result.data, Mapping)


def test_a_non_mapping_top_level_is_returned_as_is():
    assert load_text("- a\n- b\n").data == ["a", "b"]
    assert load_text("just text\n").data == "just text"


def test_two_documents_are_an_error():
    assert load_text("a: 1\n---\nb: 2\n").error


@pytest.mark.parametrize("raw", ["a: \x00\n", "\x01\x02\x03", "a: [1, 2\n", "a: 'unterminated\n", "a: *nope\n", "{{{{{{\n", "a: &x\n  b: *x\n"[:0] + "!!python/object:os.system x\n"])
def test_garbage_never_raises(raw):
    result = load_text(raw)
    assert result.error is not None or result.data is not None


def test_deep_nesting_is_an_error_not_a_crash():
    result = load_text("a: " + "[" * 5000 + "]" * 5000 + "\n")
    assert result.error is not None or result.data is not None


def test_a_big_file_parses_in_reasonable_time():
    raw = "".join(f"p{n}:\n  name: {{given: A{n}, surname: B}}\n  birth: 1850\n  parents: [x, y]\n" for n in range(10000))
    started = time.time()
    result = load_text(raw)
    assert result.error is None and len(result.data) == 10000
    assert time.time() - started < 30


def test_locate_gives_exact_spans_for_scalars():
    raw = "alder:\n  parents: [smith, alder]\nsmith: {}\n"
    root = locate(raw)
    keys = [(k.value, k.start_mark.index, k.end_mark.index) for k, _ in root.value]
    assert keys[0] == ("alder", 0, 5) and raw[keys[1][1] : keys[1][2]] == "smith"
    parents = root.value[0][1].value[0][1]
    assert [raw[n.start_mark.index : n.end_mark.index] for n in parents.value] == ["smith", "alder"]


def test_locate_returns_none_for_unreadable_text():
    assert locate("a:\n\tb: 1\n") is None
