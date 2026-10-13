from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from .dates import date_year, format_years
from .model import Person, Tree
from .privacy import is_living
from .relations import build_relations

_W_NAME, _W_ID, _W_YEAR, _W_PLACE = 3.0, 2.0, 2.0, 1.0


@dataclass
class Hit:
    id: str
    name: str
    years: str
    place: str
    parents: list[str]
    living: bool
    score: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "years": self.years,
            "place": self.place,
            "parents": self.parents,
            "living": self.living,
            "score": round(self.score, 3),
        }


def tokenize(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return [t for t in re.sub(r"[\W_]+", " ", stripped).split() if t]


def _match(query: str, token: str) -> float:
    if query == token:
        return 1.0
    if len(query) >= 2 and token.startswith(query):
        return 0.8
    if len(query) >= 3 and query in token:
        return 0.6
    if len(query) >= 3 and not query.isdigit():
        ratio = SequenceMatcher(None, query, token).ratio()
        if ratio >= 0.75:
            return ratio * 0.5
    return 0.0


def _fields(person: Person) -> list[tuple[float, list[str]]]:
    years: list[str] = []
    places: list[str] = []
    for event in (person.birth, person.death):
        if event is None:
            continue
        year = date_year(event.date)
        if year is not None:
            years.append(str(year))
        elif event.date:
            years += tokenize(event.date)
        if event.place:
            places += tokenize(event.place)
    for entry in person.partnerships:
        year = date_year(entry.start)
        if year is not None:
            years.append(str(year))
        if entry.place:
            places += tokenize(entry.place)
    names = tokenize(" ".join(part for part in (person.given, person.surname) if part))
    return [
        (_W_NAME, names),
        (_W_ID, tokenize(person.id)),
        (_W_YEAR, years),
        (_W_PLACE, places),
    ]


def search_people(tree: Tree, query: str, *, today: date, limit: int = 20) -> list[Hit]:
    words = tokenize(query)
    if not words:
        raise ValueError("empty search query")
    relations = build_relations(tree)
    hits: list[Hit] = []
    for person in tree.people.values():
        fields = _fields(person)
        total = 0.0
        for word in words:
            best = 0.0
            for weight, tokens in fields:
                for token in tokens:
                    best = max(best, weight * _match(word, token))
            if best == 0.0:
                total = 0.0
                break
            total += best
        if total == 0.0:
            continue
        birth = person.birth
        death = person.death
        place = (birth.place if birth and birth.place else None) or (death.place if death and death.place else None)
        hits.append(
            Hit(
                id=person.id,
                name=person.display_name,
                years=format_years(birth.date if birth else None, death.date if death else None),
                place=place or "",
                parents=[tree.people[p].display_name for p in relations.parents.get(person.id, [])],
                living=is_living(person, today),
                score=total,
            )
        )
    hits.sort(key=lambda h: (-h.score, h.name.lower(), h.id))
    return hits[:limit]
