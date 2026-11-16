"""Runs the family.yml conformance suite (tests/conformance) against this implementation, and checks the JSON Schema."""
import json
import re
from pathlib import Path

import pytest

from cronicl.core.check import check_tree
from cronicl.core.schema import FAMILY_SCHEMA
from cronicl.core.store import load_tree
from cronicl.core.yamltext import load_text

SUITE = Path(__file__).parent / "conformance"
VALID = sorted((SUITE / "valid").glob("*.yml"))
INVALID = sorted((SUITE / "invalid").glob("*.yml"))


def issues_of(tmp_path, text):
    (tmp_path / "family.yml").write_text(text, encoding="utf-8")
    (tmp_path / "site.yml").write_text("title: T\nschema_version: 3\n", encoding="utf-8")
    tree, load = load_tree(tmp_path)
    return check_tree(tree, load)


def expected(text):
    first = text.splitlines()[0]
    match = re.match(r"^# expect: (.+)$", first)
    assert match, f"first line must be '# expect: CODE@LINE, ...': {first!r}"
    return sorted((code, int(line)) for code, line in (item.strip().split("@") for item in match.group(1).split(",")))


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


# ---- a small validator for the subset of JSON Schema the family schema uses
def validate(value, schema, root=None):
    """Returns a list of problems (empty when `value` satisfies `schema`)."""
    root = root or schema
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return validate(value, node, root)
    if "oneOf" in schema:
        matches = [alt for alt in schema["oneOf"] if not validate(value, alt, root)]
        return [] if len(matches) >= 1 else ["matches none of the alternatives"]
    problems = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        kinds = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool, "null": type(None)}
        if not any(isinstance(value, kinds[t]) and not (t == "number" and isinstance(value, bool)) for t in types):
            return [f"{value!r} is not {types}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{value!r} not in {schema['enum']}")
    if isinstance(value, str) and "maxLength" in schema and len(value) > schema["maxLength"]:
        problems.append("too long")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        problems.append(f"{value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append("too many items")
        for item in value:
            problems += validate(item, schema.get("items", {}), root)
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                problems.append(f"missing {name}")
        for key, item in value.items():
            matched = False
            if key in schema.get("properties", {}):
                matched = True
                problems += validate(item, schema["properties"][key], root)
            for pattern, sub in schema.get("patternProperties", {}).items():
                if re.search(pattern, key):
                    matched = True
                    problems += validate(item, sub, root)
            if not matched and schema.get("additionalProperties") is False:
                problems.append(f"unexpected key {key!r}")
    return problems


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_files_have_no_issues_and_satisfy_the_schema(tmp_path, path):
    text = path.read_text(encoding="utf-8")
    assert [(i.code, i.line) for i in issues_of(tmp_path, text)] == []
    data = plain(load_text(text).data)
    assert validate(data, FAMILY_SCHEMA) == []


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_files_report_exactly_the_expected_issues(tmp_path, path):
    text = path.read_text(encoding="utf-8")
    found = sorted((i.code, i.line) for i in issues_of(tmp_path, text))
    assert found == expected(text), found
    if "# schema: rejects" in text.splitlines()[:3]:
        result = load_text(text)
        assert result.error is None and validate(plain(result.data), FAMILY_SCHEMA) != []


def test_every_check_code_of_the_spec_table_has_a_case():
    codes = {re.match(r"([EW]-[A-Z-]+?)(?:-[a-z].*)?$", p.stem).group(1) for p in INVALID}
    required = {
        "E-BAD-FAMILY", "E-RECORD-KEY", "E-RECORD-SHAPE", "E-DUPLICATE-ID", "E-COUPLE-SELF", "E-DANGLING-REF", "W-BLANK",
        "W-FLOW-COMMA", "W-DATE-UNPARSED", "W-DATE-SPAN", "W-BAD-SEX", "W-LIVING-FALSE", "W-EVENT-IS-FIELD", "W-EVENT-ONCE",
        "W-EVENT-PLACEMENT", "W-UNKNOWN-KEY", "W-DUPLICATE-KEY", "W-NO-NAME", "E-CYCLE", "W-TOO-MANY-PARENTS", "W-LIVING-AND-DEATH", "W-DUPLICATE-PARENT", "W-BIRTH-AFTER-DEATH",
        "W-CHILD-BEFORE-PARENT", "W-CHILD-AFTER-PARENT-DEATH", "W-COUPLE-EVENT-TYPE", "W-DEATH-EMPTY", "W-EVENT-NO-TYPE", "E-INVALID-ID", "W-END-BEFORE-START",
    }
    assert required <= codes, sorted(required - codes)


def test_the_schema_command_prints_the_family_schema(capsys):
    from cronicl.cli import main

    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(FAMILY_SCHEMA))


def test_init_writes_the_schema_and_the_editor_hint(tmp_path, write):
    from cronicl.cli import main

    fresh = tmp_path / "fresh"
    assert main(["init", "--dir", str(fresh)]) == 0
    assert json.loads((fresh / "family.schema.json").read_text(encoding="utf-8")) == json.loads(json.dumps(FAMILY_SCHEMA))
    assert (fresh / "family.yml").read_text(encoding="utf-8").splitlines()[0] == "# yaml-language-server: $schema=family.schema.json"
    from cronicl.checks import check_all

    assert [i for i in check_all(*load_tree(fresh)) if i.severity in ("error", "warning")] == []
