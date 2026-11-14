"""Whether a person counts as living (for privacy and for tools that ask)."""
from __future__ import annotations

from datetime import date

from .dates import latest_year
from .model import Person


def is_living(person: Person, today: date, cutoff_years: int = 100) -> bool:
    if person.living is not None:
        return person.living
    if person.death is not None:
        return False
    year = latest_year(person.birth.date) if person.birth else None
    if year is None:
        return True
    return today.year - year < cutoff_years
