from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

_PLAIN = r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?"
_CRONICL = re.compile(r"^(~?)(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")  # a plain date, or the legacy "~" approximate form
_KEYWORD = re.compile(rf"^(ABT|CAL|EST|BEF|AFT)\s+{_PLAIN}$", re.I)
_BETWEEN = re.compile(rf"^BET\s+{_PLAIN}\s+AND\s+{_PLAIN}$", re.I)
_SPAN = re.compile(rf"^(?:FROM\s+({_PLAIN})(?:\s+TO\s+({_PLAIN}))?|TO\s+({_PLAIN}))$", re.I)
_GEDCOM_PLAIN = re.compile(r"^(?:(\d{1,2})\s+)?(?:([A-Z]{3})\s+)?(\d{3,4})$")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1
    )
}


@dataclass(frozen=True)
class ParsedDate:
    year: int
    month: int | None
    day: int | None
    approx: bool
    qualifier: str | None = None  # ABT (also CAL, EST), BEF, AFT or BET
    last_year: int | None = None  # the second year of "BET a AND b"


def _ymd(year_s: str, month_s: str | None, day_s: str | None) -> tuple[int, int | None, int | None] | None:
    year = int(year_s)
    if year == 0:
        return None
    month = int(month_s) if month_s else None
    day = int(day_s) if day_s else None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None and not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return year, month, day


def _squash(text: str) -> str:
    return " ".join(text.split())


def parse_date(text: str | None) -> ParsedDate | None:
    """A date: YYYY[-MM[-DD]], optionally with ABT/CAL/EST, BEF, AFT or BET .. AND .. (any case), or the legacy ~ form."""
    if text is None:
        return None
    raw = _squash(text)
    plain = _CRONICL.match(raw)
    if plain:
        tilde, y, m, d = plain.groups()
        ymd = _ymd(y, m, d)
        return ParsedDate(*ymd, bool(tilde)) if ymd else None
    keyword = _KEYWORD.match(raw)
    if keyword:
        word, y, m, d = keyword.groups()
        ymd = _ymd(y, m, d)
        if ymd is None:
            return None
        word = word.upper()
        return ParsedDate(*ymd, True, "ABT" if word in ("ABT", "CAL", "EST") else word)
    between = _BETWEEN.match(raw)
    if between:
        y1, m1, d1, y2, m2, d2 = between.groups()
        first, last = _ymd(y1, m1, d1), _ymd(y2, m2, d2)
        if first is None or last is None:
            return None
        return ParsedDate(*first, True, "BET", last[0])
    return None


def is_unknown(text: str | None) -> bool:
    """The word `unknown` where a date belongs: it happened, when is not known."""
    return text is not None and text.strip().casefold() == "unknown"


def parse_span(text: str | None) -> tuple[str | None, str | None] | None:
    """`FROM a TO b`, `FROM a` or `TO b` as (a, b) with the end points as written; None for anything else."""
    if text is None:
        return None
    match = _SPAN.match(_squash(text))
    if not match:
        return None
    start, end_after_from, only_end = match.group(1), match.group(5), match.group(9)
    first = start
    last = end_after_from if start else only_end
    for part in (first, last):
        if part and (_CRONICL.match(part) is None or parse_date(part) is None):
            return None
    return first, last


def latest_year(text: str | None) -> int | None:
    """The latest year a birth date allows, for privacy: an uncertain date must never make a living person look dead.

    BET a AND b is b; ABT, BEF and plain dates are their year; AFT and unknown or unreadable dates give no year.
    """
    parsed = parse_date(text)
    if parsed is None or parsed.qualifier == "AFT":
        return None
    return max(parsed.year, parsed.last_year or parsed.year) if parsed.qualifier == "BET" else parsed.year


def plain_form(text: str | None) -> str | None:
    """The first date of a value without its qualifier: 'ABT 1850-03' is '1850-03'. None when unreadable."""
    parsed = parse_date(text)
    if parsed is None:
        return None
    out = f"{parsed.year:04d}"
    if parsed.month:
        out += f"-{parsed.month:02d}"
    if parsed.day:
        out += f"-{parsed.day:02d}"
    return out


def date_year(text: str | None) -> int | None:
    parsed = parse_date(text)
    return parsed.year if parsed else None


def age_between(born: ParsedDate, at: ParsedDate) -> int | None:
    """Completed years from `born` to `at`, at the finest precision both dates share; None if `at` is earlier."""
    years = at.year - born.year
    if born.month and at.month:
        if born.day and at.day:
            before_birthday = (at.month, at.day) < (born.month, born.day)
        else:
            before_birthday = at.month < born.month
        if before_birthday:
            years -= 1
    return years if years >= 0 else None


def _year_label(text: str | None) -> str:
    parsed = parse_date(text)
    if parsed is None:
        return ""
    return ("~" if parsed.approx else "") + str(parsed.year)


def format_years(birth: str | None, death: str | None) -> str:
    born, died = _year_label(birth), _year_label(death)
    if born and died:
        return f"{born}–{died}"
    if born:
        return f"b. {born}"
    if died:
        return f"d. {died}"
    return ""


def year_position(year: int, month: int | None, day: int | None) -> float:
    """A date as a decimal year, to place it on a time axis: July 1 of any year is year + 0.5."""
    if month:
        return round(year + (month - 1) / 12 + ((day or 1) - 1) / 372, 3)
    return round(year + 0.5, 3)


def _words(text: str) -> str:
    """A plain date in words: '12 March 1941'."""
    parsed = parse_date(text)
    parts = []
    if parsed.day:
        parts.append(str(parsed.day))
    if parsed.month:
        parts.append(calendar.month_name[parsed.month])
    parts.append(str(parsed.year))
    return " ".join(parts)


def format_date(text: str | None) -> str:
    """Write a date in words: '12 March 1941', 'about 1941', 'between 1880 and 1890', '1900 to 1950'.

    Unparseable text is returned as written.
    """
    if text is None:
        return ""
    raw = _squash(text)
    if is_unknown(raw):
        return "date unknown"
    span = parse_span(raw)
    if span:
        first, last = span
        if first and last:
            return f"{_words(first)} to {_words(last)}"
        return f"from {_words(first)}" if first else f"until {_words(last)}"
    parsed = parse_date(raw)
    if parsed is None:
        return raw
    if parsed.qualifier == "BET":
        first, last = (re.sub(r"^BET\s+", "", raw, flags=re.I)).split(" AND ", 1) if " AND " in raw else re.split(r"\s+and\s+", re.sub(r"^BET\s+", "", raw, flags=re.I), 1, flags=re.I)
        return f"between {_words(first)} and {_words(last)}"
    body = re.sub(r"^(?:ABT|CAL|EST|BEF|AFT)\s+", "", raw, flags=re.I).lstrip("~")
    prefix = {"ABT": "about ", "BEF": "before ", "AFT": "after "}.get(parsed.qualifier, "about " if parsed.approx else "")
    return prefix + _words(body)


def _gedcom_plain(text: str) -> str | None:
    """A GEDCOM calendar date ('12 MAR 1950', 'MAR 1950', '1950') as YYYY[-MM[-DD]], or None."""
    match = _GEDCOM_PLAIN.match(text.strip().upper())
    if not match:
        return None
    day, month, year = match.groups()
    if day and not month:
        return None
    if month and month not in _MONTHS:
        return None
    out = f"{int(year):04d}"
    if month:
        out += f"-{_MONTHS[month]:02d}"
    if day:
        out += f"-{int(day):02d}"
    return out if parse_date(out) is not None else None


def from_gedcom(text: str) -> tuple[str, bool]:
    """Convert a GEDCOM date phrase to cronicl form. Returns (value, ok); on failure value is the original text."""
    raw = text.strip()
    up = " ".join(raw.upper().split())
    keyword = re.match(r"^(ABT|CAL|EST|BEF|AFT)\s+(.+)$", up)
    if keyword:
        inner = _gedcom_plain(keyword.group(2))
        return (f"{keyword.group(1)} {inner}", True) if inner else (raw, False)
    between = re.match(r"^BET\s+(.+?)\s+AND\s+(.+)$", up)
    if between:
        first, last = _gedcom_plain(between.group(1)), _gedcom_plain(between.group(2))
        return (f"BET {first} AND {last}", True) if first and last else (raw, False)
    span = re.match(r"^FROM\s+(.+?)(?:\s+TO\s+(.+))?$", up)
    if span:
        first = _gedcom_plain(span.group(1))
        last = _gedcom_plain(span.group(2)) if span.group(2) else None
        if first and (last or not span.group(2)):
            return ("FROM " + first + (f" TO {last}" if last else ""), True)
        return raw, False
    until = re.match(r"^TO\s+(.+)$", up)
    if until:
        last = _gedcom_plain(until.group(1))
        return (f"TO {last}", True) if last else (raw, False)
    plain = _gedcom_plain(up)
    return (plain, True) if plain else (raw, False)


def to_modern(text: str | None) -> str | None:
    """The legacy `~1850` approximate form as `ABT 1850`; every other value unchanged."""
    if text and text.startswith("~"):
        return "ABT " + text[1:].strip()
    return text
