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
    "title": "famsite person frontmatter (schema_version 2)",
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
