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
        "^(?=.{1,64}$)[a-z0-9]+(-[a-z0-9]+)*$": {"$ref": "#/$defs/person"},
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
                                "also": {"oneOf": [_TEXT, {"type": "array", "items": _TEXT}]},
                            }
                        ),
                        "sex": {"oneOf": [{"type": "string", "pattern": '^([mM][aA][lL][eE]|[fF][eE][mM][aA][lL][eE]|[uU][nN][kK][nN][oO][wW][nN]|[oO][tT][hH][eE][rR])$', "description": "male, female, unknown or other, in any case"}, {"type": "null"}]},
                        "birth": _FACT,
                        "death": _FACT,
                        "parents": {"oneOf": [{"type": "null"}, {"type": "array", "items": _TEXT, "maxItems": 2}]},
                        "adoptive-parents": {"oneOf": [{"type": "null"}, {"type": "array", "items": _TEXT, "maxItems": 2}]},
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
