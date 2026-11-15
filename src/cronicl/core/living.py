"""Whether a person counts as living (for privacy and for tools that ask)."""
from __future__ import annotations

from datetime import date

from .dates import is_unknown, latest_year, parse_date, parse_span
from .model import Event, Person


def counts_as_death(death: Event | None) -> bool:
    """A death fact is evidence of death when it has a readable date, a span, `unknown` or a place; `no`, `~`, `n/a` or a bare note are not.

    Privacy fails closed: text that merely looks like "not dead" must never switch redaction off.
    """
    if death is None:
        return False
    if death.is_empty():
        return True  # an explicit but empty death record (built in code): the person died
    text = (death.date or "").strip()
    if not text:
        return bool((death.place or "").strip())  # a place alone says it happened; a note or a source alone does not
    return is_unknown(text) or parse_date(text) is not None or parse_span(text) is not None


def is_living(person: Person, today: date, cutoff_years: int = 100) -> bool:
    if person.living is not None:
        return person.living
    if counts_as_death(person.death):
        return False
    year = latest_year(person.birth.date) if person.birth else None
    if year is None:
        return True
    return today.year - year < cutoff_years
