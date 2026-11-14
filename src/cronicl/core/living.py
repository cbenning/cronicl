"""Whether a person counts as living (for privacy and for tools that ask)."""
from __future__ import annotations

from datetime import date

from .dates import parse_date
from .model import Person


def is_living(person: Person, today: date, cutoff_years: int = 100) -> bool:
    if person.living is not None:
        return person.living
    if person.death is not None:
        return False
    birth = parse_date(person.birth.date) if person.birth else None
    if birth is None:
        return True
    return today.year - birth.year < cutoff_years
