from __future__ import annotations

_EVENT = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "YYYY, YYYY-MM, YYYY-MM-DD, optional leading ~ for approximate"},
        "place": {"type": "string"},
    },
    "additionalProperties": True,
}

_ID = {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64}

PERSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "cronicl person frontmatter (schema_version 2)",
    "type": "object",
    "properties": {
        "id": _ID,
        "name": {
            "oneOf": [
                {"type": "string"},
                {"type": "object", "properties": {"given": {"type": "string"}, "surname": {"type": "string"}}},
            ]
        },
        "sex": {"enum": ["M", "F", "U"]},
        "birth": _EVENT,
        "death": _EVENT,
        "living": {"type": "boolean"},
        "portrait": {"type": "string", "description": "file under media/ shown as this person's picture"},
        "gallery_id": {"type": "string", "description": "this person's id in the photo gallery (a Fussel slug); overrides matching by name"},
        "parents": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 2,
            "description": "ids of this person's birth parents (up-reference)",
        },
        "spouse": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ids of spouses; needed only for a couple with no children and no partnerships entry",
        },
        "children": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ids of children (down-reference, merged into each child's parents)",
        },
        "partnerships": {
            "type": "array",
            "description": "relationships with another person; may be declared on either partner and are merged",
            "items": {
                "type": "object",
                "properties": {
                    "with": {"type": "string"},
                    "type": {"enum": ["marriage", "civil-union", "partnership", "engagement", "unknown"]},
                    "start": {"type": "string", "description": "date the partnership began"},
                    "end": {"type": "string", "description": "date it ended, or the word unknown"},
                    "end_reason": {"enum": ["divorce", "annulment", "separation"]},
                    "place": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["with"],
            },
        },
        "marriages": {
            "type": "array",
            "deprecated": True,
            "description": "legacy: read as partnerships of type marriage; fix --apply migrates it",
            "items": {
                "type": "object",
                "properties": {
                    "with": {"type": "string"},
                    "date": {"type": "string"},
                    "place": {"type": "string"},
                },
                "required": ["with"],
            },
        },
        "events": {
            "type": "array",
            "description": "events and attributes beyond birth and death: occupation, burial, immigration, ...",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "a slug such as occupation, burial, immigration"},
                    "date": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "place": {"type": "string"},
                    "value": {"type": "string", "description": "for attributes such as occupation"},
                    "note": {"type": "string"},
                    "cite": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                },
                "required": ["type"],
                "additionalProperties": True,
            },
        },
        "gedcom_id": {"type": "string"},
        "gedcom_extra": {"type": "string"},
        "media": {"description": "reserved for the gallery; preserved and ignored"},
    },
    "additionalProperties": True,
}


# ---- the schema of family.yml (draft 2020-12). Values are text however they are typed, so every scalar is allowed.
_TEXT = {"type": ["string", "number", "boolean", "null"]}
_X = {"^[xX][-_]": {}}  # the owner's own keys, allowed everywhere


def _object(properties: dict, required: list | None = None) -> dict:
    out = {"type": "object", "properties": properties, "patternProperties": _X, "additionalProperties": False}
    if required:
        out["required"] = required
    return out


_FACT = {
    "oneOf": [
        _TEXT,
        _object({"date": _TEXT, "place": _TEXT, "note": _TEXT, "cite": {"oneOf": [_TEXT, {"type": "array", "items": _TEXT}]}}),
    ],
    "description": "a date, or a mapping with date, place, note and cite",
}
_EVENT = _object(
    {
        "type": {"type": "string", "description": "a slug such as occupation, residence, burial; couples: marriage, divorce, ..."},
        "date": {**_TEXT, "description": "YYYY[-MM[-DD]], ABT/BEF/AFT/BET .. AND .., FROM .. TO .., or unknown"},
        "place": _TEXT,
        "value": _TEXT,
        "note": _TEXT,
        "cite": {"oneOf": [_TEXT, {"type": "array", "items": _TEXT}]},
    },
    required=["type"],
)

FAMILY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "cronicl family.yml",
    "description": "Every top-level key is a person id, or two person ids joined by + (a couple).",
    "type": "object",
    "patternProperties": {
        "^[a-z0-9]+(-[a-z0-9]+)*$": {"$ref": "#/$defs/person"},
        r"^\s*[a-z0-9]+(-[a-z0-9]+)*\s*\+\s*[a-z0-9]+(-[a-z0-9]+)*\s*$": {"$ref": "#/$defs/couple"},
    },
    "additionalProperties": False,
    "$defs": {
        "person": {
            "oneOf": [
                {"type": "null"},
                {"type": "string", "maxLength": 0},
                _object(
                    {
                        "name": _object(
                            {
                                "given": _TEXT,
                                "surname": _TEXT,
                                "prefix": _TEXT,
                                "suffix": _TEXT,
                                "nickname": _TEXT,
                                "also": {"type": "array", "items": _TEXT},
                            }
                        ),
                        "sex": {"oneOf": [{"enum": ["male", "female", "unknown", "other"]}, {"type": "null"}]},
                        "birth": _FACT,
                        "death": _FACT,
                        "parents": {"oneOf": [{"type": "null"}, {"type": "array", "items": _TEXT, "maxItems": 2}]},
                        "events": {"oneOf": [{"type": "null"}, {"type": "array", "items": _EVENT}]},
                        "portrait": _TEXT,
                        "living": _TEXT,
                        "refs": _object({"gedcom": _TEXT, "gallery": _TEXT}),
                        "bio": _TEXT,
                    }
                ),
            ]
        },
        "couple": {
            "oneOf": [
                {"type": "null"},
                {"type": "string", "maxLength": 0},
                _object({"events": {"oneOf": [{"type": "null"}, {"type": "array", "items": _EVENT}]}, "note": _TEXT}),
            ]
        },
    },
}
