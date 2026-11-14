import pytest

from cronicl.core.dates import date_year, format_years, from_gedcom, parse_date


def test_parse_full_partial_and_approximate():
    full = parse_date("1950-03-12")
    assert (full.year, full.month, full.day, full.approx) == (1950, 3, 12, False)
    partial = parse_date("1950-03")
    assert (partial.month, partial.day) == (3, None)
    approx = parse_date("~1850")
    assert approx.year == 1850 and approx.approx


@pytest.mark.parametrize("bad", ["", "1950-13", "1950-02-30", "12 MAR 1950", "0000", "abc", None])
def test_parse_rejects_invalid(bad):
    assert parse_date(bad) is None


def test_date_year():
    assert date_year("1950-03-12") == 1950
    assert date_year("nonsense") is None


def test_format_years():
    assert format_years("1950-03-12", "2020-07-01") == "1950–2020"
    assert format_years("1950", None) == "b. 1950"
    assert format_years(None, "2020") == "d. 2020"
    assert format_years(None, None) == ""
    assert format_years("~1850", "~1910") == "~1850–~1910"
    assert format_years("BET 1900 AND 1910", None) == ""


@pytest.mark.parametrize(
    "gedcom,expected",
    [
        ("12 MAR 1950", "1950-03-12"),
        ("MAR 1950", "1950-03"),
        ("1950", "1950"),
        ("ABT 1850", "~1850"),
        ("abt 12 mar 1850", "~1850-03-12"),
    ],
)
def test_from_gedcom_converts(gedcom, expected):
    assert from_gedcom(gedcom) == (expected, True)


@pytest.mark.parametrize("gedcom", ["BET 1900 AND 1910", "32 MAR 1950", "@#DJULIAN@ 12 MAR 1750", "1750/51", "12 1950"])
def test_from_gedcom_keeps_unparsable_text(gedcom):
    assert from_gedcom(gedcom) == (gedcom, False)


from cronicl.core.dates import age_between  # noqa: E402


def age(born, at):
    return age_between(parse_date(born), parse_date(at))


def test_age_from_years_only():
    assert age("1950", "1990") == 40


def test_age_by_month_when_both_have_a_month():
    assert age("1950-06", "1990-05") == 39
    assert age("1950-06", "1990-06") == 40
    assert age("1950-12", "1951-01") == 0


def test_age_by_day_when_both_have_a_day():
    assert age("1950-06-15", "1990-06-14") == 39
    assert age("1950-06-15", "1990-06-15") == 40


def test_age_falls_back_to_the_finest_precision_both_share():
    assert age("1950-06-15", "1990-06") == 40
    assert age("1950", "1990-05-01") == 40


def test_age_is_none_before_birth():
    assert age("1990", "1980") is None


from cronicl.core.dates import format_date


@pytest.mark.parametrize("text, expected", [
    ("1941-03-12", "12 March 1941"),
    ("1941-01", "January 1941"),
    ("1941", "1941"),
    ("~1941", "about 1941"),
    ("~1941-03-12", "about 12 March 1941"),
    ("APR 4 TH 2020", "APR 4 TH 2020"),
    ("  1941  ", "1941"),
    ("", ""),
    (None, ""),
])
def test_format_date(text, expected):
    assert format_date(text) == expected


@pytest.mark.parametrize("birth, death, expected", [
    ("1941-03-12", "2021", "1941–2021"),
    ("1907", None, "b. 1907"),
    (None, "1990-02", "d. 1990"),
    ("~1907", None, "b. ~1907"),
    ("~1850", "~1910", "~1850–~1910"),
    ("garbage", None, ""),
    (None, None, ""),
])
def test_format_years_never_prints_an_open_dash(birth, death, expected):
    assert format_years(birth, death) == expected


from cronicl.core.dates import year_position


def test_year_position():
    assert year_position(1900, None, None) == 1900.5
    assert year_position(1900, 7, 1) == 1900.5
    assert year_position(1900, 1, None) == 1900.0
    assert year_position(1900, 12, 31) == 1900.997
