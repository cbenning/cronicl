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


PARTNERSHIP_TYPES = ("marriage", "civil-union", "partnership", "engagement", "unknown")
END_REASONS = ("divorce", "annulment", "separation")


@dataclass
class Partnership:
    with_id: str  # "" for an entry that names no partner
    type: str | None = None  # one of PARTNERSHIP_TYPES; None when the file does not say
    start: str | None = None
    end: str | None = None  # a date, or the word "unknown"
    end_reason: str | None = None
    place: str | None = None
    note: str | None = None
    cite: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    distinct: bool = False  # read from a couple's events: one partnership of its own, never merged with another


@dataclass
class LifeEvent:
    """An event or attribute beyond birth and death: occupation, burial, immigration, residence, ..."""

    type: str = ""
    date: str | None = None
    start: str | None = None
    end: str | None = None
    place: str | None = None
    value: str | None = None
    note: str | None = None
    cite: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class Person:
    id: str
    given: str | None = None
    surname: str | None = None
    name_extra: dict = field(default_factory=dict)
    prefix: str | None = None
    suffix: str | None = None
    nickname: str | None = None
    also: list[str] = field(default_factory=list)  # other names (a married name, ...), searchable
    sex: str = "U"
    sex_text: str | None = None  # the `sex` value as written in family.yml, for validation only
    birth: Event | None = None
    death: Event | None = None
    living: bool | None = None
    living_text: str | None = None  # the `living` value as written (None when absent), for validation only
    portrait: str | None = None
    gallery_id: str | None = None
    parents: list[str] = field(default_factory=list)
    spouse: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    partnerships: list[Partnership] = field(default_factory=list)
    events: list[LifeEvent] = field(default_factory=list)
    gedcom_id: str | None = None
    gedcom_extra: str | None = None
    body: str = ""
    extra: dict = field(default_factory=dict)
    path: Path | None = None
    id_pinned: bool = False
    source: str | None = None  # family.yml (or family/x.yml), relative to the data folder; None for the legacy layout
    line: int | None = None  # the line of this person's record in `source`
    couple_records: list = field(default_factory=list)  # (partner id, raw couple record, source, line) filed under this person
    raw: object = None  # the record as loaded from family.yml (a yamltext.Mapping), for validation; never written back

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.prefix, self.given, self.surname, self.suffix) if part) or self.id

    @property
    def initials(self) -> str:
        letters = [(self.given or "").strip()[:1], (self.surname or "").strip()[:1]]
        return "".join(letter.upper() for letter in letters if letter) or "?"

    @property
    def location(self) -> str | None:
        if self.source is not None:
            return self.source
        if self.path is None:
            return None
        return f"{self.path.parent.name}/{self.path.name}"


@dataclass
class Tree:
    people: dict[str, Person] = field(default_factory=dict)
    site: dict = field(default_factory=dict)
