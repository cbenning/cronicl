"""Whether a person counts as living (for privacy and for tools that ask)."""
from __future__ import annotations

from datetime import date

from .dates import is_unknown, latest_year, parse_date, parse_span
from .model import Event, Person


def counts_as_death(death: Event | None) -> bool:
    """A death fact is evidence of death unless its date is something that is not a date (`no`, `~`, `n/a`).

    Privacy fails closed: text that merely looks like "not dead" must never switch redaction off.
    """
    if death is None:
        return False
    text = (death.date or "").strip()
    return not text or is_unknown(text) or parse_date(text) is not None or parse_span(text) is not None


def is_living(person: Person, today: date, cutoff_years: int = 100) -> bool:
    if person.living is not None:
        return person.living
    if counts_as_death(person.death):
        return False
    year = latest_year(person.birth.date) if person.birth else None
    if year is None:
        return True
    return today.year - year < cutoff_years
