from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Event:
    date: str | None = None
    place: str | None = None
    extra: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.date or self.place or self.extra)


@dataclass
class Marriage:
    with_id: str  # "" for an entry that names no partner
    date: str | None = None
    place: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Person:
    id: str
    given: str | None = None
    surname: str | None = None
    name_extra: dict = field(default_factory=dict)
    sex: str = "U"
    birth: Event | None = None
    death: Event | None = None
    living: bool | None = None
    parents: list[str] = field(default_factory=list)
    spouse: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    marriages: list[Marriage] = field(default_factory=list)
    gedcom_id: str | None = None
    gedcom_extra: str | None = None
    body: str = ""
    extra: dict = field(default_factory=dict)
    path: Path | None = None
    id_pinned: bool = False

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.given, self.surname) if part) or self.id

    @property
    def location(self) -> str | None:
        if self.path is None:
            return None
        return f"{self.path.parent.name}/{self.path.name}"


@dataclass
class Tree:
    people: dict[str, Person] = field(default_factory=dict)
    site: dict = field(default_factory=dict)
