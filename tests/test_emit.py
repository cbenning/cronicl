import random

import pytest

from cronicl.core import emit
from cronicl.core.store import load_tree

NASTY = [
    "a, b", "x: y", "# not a comment", " lead", "trail ", "NO", "1066", "null", "~", "true", "- dash", "-dash", "[x]", "{x}",
    "it's", 'say "hi"', "multi\nline", "tab\there", "é ñ 日本 🌳", "a #b", "*star", "&amp", "!tag", "%pct", "@at", "`tick",
    "|pipe", ">gt", "?q", "key:", ":lead", "0123", "1e3", "2020-01-01", "back\\slash", "ends with colon:", "a: b: c",
    "x\u2028y", "'single'", '"double"', "a,b,c", "{a: b}", "[1, 2]", "-", "?", "--- ", "...", "=", "<<", "plain words",
]


def round_trip(tmp_path, write_family, spec_by_id, couples=()):
    text = emit.family(list(spec_by_id.items()), list(couples))
    write_family(tmp_path, text)
    tree, issues = load_tree(tmp_path)
    assert [i for i in issues if i.severity == "error"] == [], (text, issues)
    return tree, text


@pytest.mark.parametrize("text", NASTY)
def test_awkward_text_reads_back_exactly(tmp_path, write_family, text):
    spec = {
        "name": {"given": text, "surname": "S", "also": [text, "plain"]},
        "birth": {"date": "1850", "place": text, "note": text, "cite": [text, "second"]},
        "death": {"date": "1900", "place": text},
        "events": [{"type": "occupation", "value": text, "note": text, "cite": text, "place": text}],
        "x": {"x-note": text},
        "refs": {"gedcom": text, "gallery": text},
        "portrait": text,
    }
    tree, source = round_trip(tmp_path, write_family, {"a": spec})
    a = tree.people["a"]
    assert a.given == (text.strip() or None), source
    assert a.also == [t for t in (text.strip(), "plain") if t]
    assert a.birth.place == text.strip() or not text.strip()
    assert a.birth.extra["note"] == text.replace("\r", "") or not text.strip()
    assert a.events[0].value == text.strip() and a.events[0].cite == [text.strip()]
    assert a.extra["x-note"] == text
    assert a.gedcom_id == text.strip() and a.gallery_id == text.strip()
    assert a.portrait == text.strip()


@pytest.mark.parametrize("bio", ["Words.", "A\n\nB: c\n\n  indented\n\nD", "  leading space first", "tab\tinside", "ends here   \nspaces", "# heading\n- list\n- items", "x"])
def test_bios_read_back(tmp_path, write_family, bio):
    tree, source = round_trip(tmp_path, write_family, {"a": {"name": {"given": "A"}, "bio": bio}})
    assert tree.people["a"].body == bio.strip("\n"), source


def test_a_lone_date_is_written_bare_and_others_as_a_flow_mapping():
    text = emit.person("a", {"name": {"given": "A"}, "birth": "1850", "death": {"date": "1900", "place": "X, Y"}})
    assert "  birth: 1850\n" in text and '  death: {date: 1900, place: "X, Y"}\n' in text


def test_a_long_fact_becomes_a_block():
    place = "A very long place name, " * 6
    text = emit.person("a", {"name": {"given": "A"}, "birth": {"date": "1850", "place": place}})
    assert "  birth:\n    date: 1850\n    place: " in text


def test_spans_are_written_as_from_to():
    text = emit.person("a", {"events": [{"type": "residence", "start": "1900", "end": "1910"}, {"type": "residence", "start": "1920"}, {"type": "x", "end": "1930"}]})
    assert "date: FROM 1900 TO 1910" in text and "date: FROM 1920}" in text and "date: TO 1930}" in text


def test_couples_are_sorted_and_an_empty_one_is_braces():
    assert emit.couple("b", "a") == "a + b: {}\n"
    assert emit.couple("b", "a", {"events": [{"type": "marriage", "date": "1900"}], "note": "n"}) == (
        "a + b:\n  events:\n    - {type: marriage, date: 1900}\n  note: n\n"
    )


def test_family_puts_each_couple_after_its_second_partner():
    text = emit.family(
        [("b", {"name": {"given": "B"}}), ("a", {"name": {"given": "A"}}), ("c", {"name": {"given": "C"}})],
        [("c", "a", {}), ("a", "b", {"note": "n"}), ("a", "ghost", {})],
    )
    order = [line.split(":")[0] for line in text.splitlines() if line and not line.startswith(" ")]
    assert order == ["a", "a + b", "b", "a + c", "c", "a + ghost"] or order == ["a", "b", "a + b", "c", "a + c", "a + ghost"]


def test_random_records_round_trip(tmp_path, write_family):
    rng = random.Random(7)
    alphabet = list("abc XYZ,:#-[]{}'\"\\é日🌳\t") + ["NO", "1066", ": ", " #"]
    for case in range(60):
        word = lambda: "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 12))).strip() or "x"
        values = [word() for _ in range(5)]
        spec = {"name": {"given": values[0], "surname": values[1]}, "birth": {"date": "1850", "place": values[2]},
                "events": [{"type": "job", "value": values[3], "note": values[4]}], "x": {"x-k": values[4]}}
        tree, source = round_trip(tmp_path / f"c{case}", write_family, {"a": spec})
        a = tree.people["a"]
        assert (a.given, a.surname, a.birth.place, a.events[0].value, a.events[0].note, a.extra["x-k"]) == (
            values[0], values[1], values[2], values[3], values[4], values[4]
        ), source
