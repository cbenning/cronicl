"""Loading and checking a family from text gives the same answers as loading it from disk."""
from pathlib import Path

import pytest

from cronicl.checks import check_all
from cronicl.checktext import check_texts, load_tree_from_texts
from cronicl.core.store import load_tree

SUITE = Path(__file__).parent / "conformance"
FILES = sorted((SUITE / "valid").glob("*.yml")) + sorted((SUITE / "invalid").glob("*.yml"))
SITE = "title: T\nschema_version: 3\n"


def disk_issues(tmp_path, text):
    (tmp_path / "family.yml").write_text(text, encoding="utf-8")
    (tmp_path / "site.yml").write_text(SITE, encoding="utf-8")
    tree, load = load_tree(tmp_path)
    return sorted((i.code, i.line, i.path) for i in check_all(tree, load))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_text_and_disk_agree_on_every_conformance_file(tmp_path, path):
    text = path.read_text(encoding="utf-8")
    from_text = sorted((i.code, i.line, i.path) for i in check_texts(SITE, {"family.yml": text}, tmp_path))
    assert from_text == disk_issues(tmp_path, text)


def test_a_family_folder_of_two_files_loads_from_text(tmp_path):
    tree, issues = load_tree_from_texts(SITE, {"family/one.yml": "a: {name: {given: A}}\n", "family/two.yml": "b: {name: {given: B}, parents: [a]}\n"}, tmp_path)
    assert sorted(tree.people) == ["a", "b"] and issues == []
    assert tree.people["b"].source == "family/two.yml"


def test_family_yml_and_a_folder_together_are_an_error(tmp_path):
    _, issues = load_tree_from_texts(SITE, {"family.yml": "a: {}\n", "family/x.yml": "b: {}\n"}, tmp_path)
    assert [i.code for i in issues] == ["E-BAD-FAMILY"]


def test_site_yml_text_problems_are_reported(tmp_path):
    issues = check_texts("title: [unclosed\n", {"family.yml": "a: {name: {given: A}}\n"}, tmp_path)
    assert "E-BAD-SITE-YML" in [i.code for i in issues]


def test_no_site_yml_text_uses_defaults_with_the_usual_warning(tmp_path):
    issues = check_texts(None, {"family.yml": "a: {name: {given: A}}\n"}, tmp_path)
    assert [i.code for i in issues] == ["W-NO-SITE-YML"]
