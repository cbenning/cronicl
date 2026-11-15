"""Every field of a family record, described once: the TUI builds its editors and its field palette from this table.

`tests/test_catalog.py` pins it to the JSON Schema, so it cannot drift from the format (SPEC.md sections 4 and 5).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    path: str  # `name.given`, `birth.date`, `events[].type`; a group (`birth`) has kind "group"
    kind: str  # text | longtext | date | choice | people | file | place | flag | list | group
    description: str
    applies: str = "person"  # person | couple | both
    once: bool = True  # at most one; False for lists
    choices: tuple | None = None


SEX_WORDS = ("male", "female", "unknown", "other")


def _f(path, kind, description, applies="person", once=True, choices=None) -> tuple[str, Field]:
    return path, Field(path, kind, description, applies, once, choices)


FIELDS: dict[str, Field] = dict([
    _f("name", "group", "the person's name, in parts"),
    _f("name.given", "text", "given (first and middle) names"),
    _f("name.surname", "text", "family name"),
    _f("name.prefix", "text", "a title before the name, such as Dr. or Lady"),
    _f("name.suffix", "text", "a title after the name, such as Jr. or III"),
    _f("name.nickname", "text", "a name people use for them"),
    _f("name.also", "list", "other names: a married name, a spelling used elsewhere (searchable)", once=False),
    _f("sex", "choice", "male, female, unknown or other", choices=SEX_WORDS),
    _f("birth", "group", "when and where they were born"),
    _f("birth.date", "date", "birth date (1850, 1850-03-15, ABT 1850, BET 1880 AND 1890, unknown)"),
    _f("birth.place", "place", "birthplace, as text (Ockham, Surrey)"),
    _f("birth.note", "longtext", "a remark shown with the birth"),
    _f("birth.cite", "list", "where the birth is recorded: a source text", once=False),
    _f("death", "group", "when and where they died"),
    _f("death.date", "date", "death date; `unknown` says they died, date not known"),
    _f("death.place", "place", "place of death"),
    _f("death.note", "longtext", "a remark shown with the death"),
    _f("death.cite", "list", "where the death is recorded: a source text", once=False),
    _f("parents", "people", "birth parents: at most two people", once=False),
    _f("events", "list", "things that happened: occupation, residence, burial, ...", "both", once=False),
    _f("events[].type", "choice", "what kind of event (any word; hyphens read as spaces)", "both"),
    _f("events[].date", "date", "when it happened (FROM 1835 TO 1852 for something that lasted)", "both"),
    _f("events[].place", "place", "where it happened", "both"),
    _f("events[].value", "text", "the content of an attribute, such as the occupation", "both"),
    _f("events[].note", "longtext", "a remark about the event", "both"),
    _f("events[].cite", "list", "where it is recorded: a source text", "both", once=False),
    _f("portrait", "file", "a picture file in media/"),
    _f("living", "flag", "true says they are alive even if their dates suggest otherwise"),
    _f("refs", "group", "ids in other systems"),
    _f("refs.gedcom", "text", "their record id in an imported GEDCOM file"),
    _f("refs.gallery", "text", "their id in the photo gallery"),
    _f("bio", "longtext", "their story, written as markdown"),
    _f("note", "longtext", "a remark about the couple", "couple"),
])

def _addable(field: Field) -> bool:
    """Can this be added to a record from the palette? Name and refs parts, birth and death, and the top-level fields."""
    if "[]" in field.path:
        return False  # event parts are edited inside an event
    head, _, rest = field.path.partition(".")
    if field.kind == "group":
        return field.path in ("birth", "death")
    return not rest or head in ("name", "refs")


def fields_for(kind: str) -> list[Field]:
    """The fields a `person` or `couple` record can take, in canonical order, for the field palette."""
    return [f for f in FIELDS.values() if _addable(f) and f.applies in (kind, "both")]


EVENT_TYPES: dict[str, str] = {
    "occupation": "a job or trade (put the job in the value)",
    "residence": "a place they lived",
    "burial": "where and when they were buried",
    "cremation": "when and where they were cremated",
    "baptism": "a baptism",
    "christening": "a christening",
    "confirmation": "a confirmation",
    "immigration": "arriving in a new country",
    "emigration": "leaving a country",
    "naturalization": "becoming a citizen",
    "education": "schooling (put the school in the value)",
    "graduation": "finishing a course or degree",
    "religion": "their religion (in the value)",
    "nationality": "their nationality (in the value)",
    "retirement": "retiring from work",
    "census": "appearing in a census",
    "will": "making a will",
    "probate": "their will being proved",
}

COUPLE_EVENT_TYPES: dict[str, str] = {
    "marriage": "they married",
    "engagement": "they became engaged",
    "civil-union": "a civil union",
    "partnership": "they became partners",
    "separation": "they separated",
    "divorce": "they divorced",
    "annulment": "the marriage was annulled",
    "end": "the relationship ended, the reason is not known",
    "residence": "a place they lived together",
    "census": "appearing together in a census",
}
