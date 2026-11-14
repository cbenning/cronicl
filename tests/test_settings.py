import pytest

from famsite.settings import MODES, parse_bool, parse_int, place_groups, privacy_settings, site_text


@pytest.mark.parametrize("value", ["true", " YES ", "On", "1", True])
def test_parse_bool_true(value):
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["false", "No", "OFF", "0", False])
def test_parse_bool_false(value):
    assert parse_bool(value) is False


@pytest.mark.parametrize("value", ["maybe", "", None, 2, []])
def test_parse_bool_none(value):
    assert parse_bool(value) is None


@pytest.mark.parametrize("value, expected", [("100", 100), (" 100 ", 100), ("+5", 5), (7, 7)])
def test_parse_int_accepts(value, expected):
    assert parse_int(value) == expected


@pytest.mark.parametrize("value", ["100.0", "1e2", "-5", "1_000", "0", True, None, [], "abc", ""])
def test_parse_int_rejects(value):
    assert parse_int(value) is None


def test_modes():
    assert MODES == ("full", "placeholder", "hidden")


@pytest.mark.parametrize("site", [{}, {"privacy": {}}, {"privacy": {"cutoff_years": "25"}}])
def test_no_living_setting_is_full_and_not_broken(site):
    p = privacy_settings(site)
    assert (p.living, p.broken) == ("full", False)


@pytest.mark.parametrize("word, mode", [("Placeholder", "placeholder"), (" hidden ", "hidden"), ("FULL", "full")])
def test_mode_words_ignore_case_and_spaces(word, mode):
    p = privacy_settings({"privacy": {"living": word}})
    assert (p.living, p.broken) == (mode, False)


@pytest.mark.parametrize(
    "site",
    [
        {"privacy": "hidden"},
        {"privacy": ["a"]},
        {"privacy": {"living": "nope"}},
        {"privacy": {"living": ""}},
        {"privacy": {"living": None}},
        {"_unreadable": True},
    ],
)
def test_broken_privacy_fails_closed(site):
    p = privacy_settings(site)
    assert (p.living, p.broken) == ("placeholder", True)


@pytest.mark.parametrize("value, expected", [("abc", 100), ("100.0", 100), (-5, 100), ("25", 25), (25, 25), (None, 100)])
def test_cutoff_years(value, expected):
    assert privacy_settings({"privacy": {"cutoff_years": value}}).cutoff_years == expected


def test_salt_is_text_or_empty():
    assert privacy_settings({"privacy": {"id_salt": "s"}}).salt == "s"
    assert privacy_settings({"privacy": {}}).salt == ""
    assert privacy_settings({"privacy": {"id_salt": None}}).salt == ""
    for bad in (["x"], {"a": 1}):
        p = privacy_settings({"privacy": {"living": "hidden", "id_salt": bad}})
        assert (p.salt, p.broken) == ("", True)


def test_site_text():
    assert site_text({"title": "T"}, "title") == "T"
    assert site_text({"title": 1066}, "title") == "1066"
    assert site_text({}, "title", "Family Tree") == "Family Tree"
    assert site_text({"title": "  "}, "title", "D") == "D"
    assert site_text({"title": ["a"]}, "title", "D") == "D"
    assert site_text({"title": {"a": 1}}, "title", "D") == "D"


def test_place_groups_keeps_only_text_pairs():
    assert place_groups({"place_groups": {"Ontario": "Canada", "X": ["a"], "Y": None}}) == {"Ontario": "Canada"}
    assert place_groups({"place_groups": "Ontario"}) == {}
    assert place_groups({}) == {}
