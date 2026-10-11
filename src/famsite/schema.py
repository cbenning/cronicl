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
    "title": "famsite person frontmatter (schema_version 1)",
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
        "parents": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 2,
            "description": "ids of this person's birth parents (up-reference)",
        },
        "spouse": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ids of spouses; needed only for a couple with no children and no marriages entry",
        },
        "children": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ids of children (down-reference, merged into each child's parents)",
        },
        "marriages": {
            "type": "array",
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
        "gedcom_id": {"type": "string"},
        "gedcom_extra": {"type": "string"},
        "media": {"description": "reserved; preserved but ignored in v0.1"},
    },
    "additionalProperties": True,
}
