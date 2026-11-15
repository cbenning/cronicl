import pytest

from cronicl.core.dates import from_gedcom, to_gedcom


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1850", "1850"),
        ("1850-03", "MAR 1850"),
        ("1850-03-15", "15 MAR 1850"),
        ("0900-01-02", "2 JAN 900"),
        ("ABT 1850-03", "ABT MAR 1850"),
        ("cal 1850", "CAL 1850"),
        ("BEF 1920-12-31", "BEF 31 DEC 1920"),
        ("BET 1880 AND 1890-05", "BET 1880 AND MAY 1890"),
        ("FROM 1900 TO 1950", "FROM 1900 TO 1950"),
        ("FROM 1900-06", "FROM JUN 1900"),
        ("TO 1950", "TO 1950"),
    ],
)
def test_to_gedcom_writes_gedcom_dates_that_read_back_the_same(text, expected):
    assert to_gedcom(text) == expected
    value, ok = from_gedcom(expected)
    assert ok and value == " ".join(text.upper().split())


@pytest.mark.parametrize("text", [None, "", "unknown", "  unknown "])
def test_nothing_or_unknown_writes_no_date(text):
    assert to_gedcom(text) is None


@pytest.mark.parametrize("text", ["around the turn of the century", "19x0", "~1850"])
def test_unreadable_dates_are_returned_as_written(text):
    assert to_gedcom(text) == text
