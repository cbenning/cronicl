"""The field catalog describes every field of the format once; it must not drift from the JSON Schema."""
from cronicl.core.catalog import COUPLE_EVENT_TYPES, EVENT_TYPES, FIELDS, fields_for
from cronicl.core.schema import FAMILY_SCHEMA


def _props(schema):
    """The property names of an object schema, looking through oneOf."""
    if "properties" in schema:
        return schema["properties"]
    for alt in schema.get("oneOf", []):
        if "properties" in alt:
            return alt["properties"]
    return {}


def schema_paths(record: dict) -> set[str]:
    out = set()
    for key, sub in _props(record).items():
        nested = _props(sub)
        if key == "events":
            items = (sub.get("oneOf", [{}, {}])[1])["items"]
            out.add("events")
            out |= {f"events[].{k}" for k in items["properties"]}
        elif nested:
            out |= {f"{key}.{k}" for k in nested}
        else:
            out.add(key)
    return out


def test_every_schema_field_has_a_catalog_entry_and_the_reverse():
    person = FAMILY_SCHEMA["$defs"]["person"]
    couple = FAMILY_SCHEMA["$defs"]["couple"]
    expected = schema_paths(person) | schema_paths(couple)
    leaves = {path for path, field in FIELDS.items() if field.kind != "group"}
    assert expected == leaves, (sorted(expected - leaves), sorted(leaves - expected))


def test_every_field_has_a_description_and_a_known_kind():
    for path, field in FIELDS.items():
        assert field.path == path and field.description.strip(), path
        assert field.kind in {"text", "longtext", "date", "choice", "people", "file", "place", "group", "flag", "list"}, path
        assert field.applies in ("person", "couple", "both"), path


def test_sex_choices_are_the_four_words():
    assert FIELDS["sex"].choices == ("male", "female", "unknown", "other")


def test_event_types_have_descriptions_and_cover_the_importer():
    for slug in ("residence", "occupation", "burial", "immigration", "baptism", "census"):
        assert EVENT_TYPES[slug].strip()
    for slug in ("marriage", "divorce", "engagement", "civil-union", "partnership", "separation", "annulment", "end"):
        assert COUPLE_EVENT_TYPES[slug].strip()


def test_fields_for_lists_what_a_record_can_take_without_event_subfields():
    person = {f.path for f in fields_for("person")}
    assert {"name.nickname", "sex", "birth", "death", "parents", "events", "bio", "living", "portrait", "refs.gedcom"} <= person
    assert not any("[]" in p for p in person)
    couple = {f.path for f in fields_for("couple")}
    assert couple == {"events", "note"}
