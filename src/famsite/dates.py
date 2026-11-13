from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

_FAMSITE = re.compile(r"^(~?)(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_GEDCOM = re.compile(r"^(?:(ABT|CAL|EST)\s+)?(?:(\d{1,2})\s+)?(?:([A-Z]{3})\s+)?(\d{3,4})$")
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


def parse_date(text: str | None) -> ParsedDate | None:
    if text is None:
        return None
    match = _FAMSITE.match(text.strip())
    if not match:
        return None
    approx, year_s, month_s, day_s = match.groups()
    year = int(year_s)
    if year == 0:
        return None
    month = int(month_s) if month_s else None
    day = int(day_s) if day_s else None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None and not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return ParsedDate(year, month, day, bool(approx))


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


def format_date(text: str | None) -> str:
    """Write a date in words: '12 March 1941', 'about 1941'. Unparseable text is returned as written."""
    if text is None:
        return ""
    raw = text.strip()
    parsed = parse_date(raw)
    if parsed is None:
        return raw
    parts = []
    if parsed.day:
        parts.append(str(parsed.day))
    if parsed.month:
        parts.append(calendar.month_name[parsed.month])
    parts.append(str(parsed.year))
    return ("about " if parsed.approx else "") + " ".join(parts)


def from_gedcom(text: str) -> tuple[str, bool]:
    """Convert a GEDCOM date to famsite form. Returns (value, ok); on failure value is the original text."""
    raw = text.strip()
    match = _GEDCOM.match(raw.upper())
    if not match:
        return raw, False
    qualifier, day, month, year = match.groups()
    if day and not month:
        return raw, False
    if month and month not in _MONTHS:
        return raw, False
    out = f"{int(year):04d}"
    if month:
        out += f"-{_MONTHS[month]:02d}"
    if day:
        out += f"-{int(day):02d}"
    if qualifier:
        out = "~" + out
    if parse_date(out) is None:
        return raw, False
    return out, True
