import pytest

from famsite.dates import date_year, format_years, from_gedcom, parse_date


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
    assert format_years("1950", None) == "1950–"
    assert format_years(None, "2020") == "–2020"
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
