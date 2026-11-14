import pytest

from cronicl.core.store import load_site, load_tree


def test_missing_site_yml_is_a_warning(tmp_path):
    _, issues = load_site(tmp_path)
    assert [i.code for i in issues] == ["W-NO-SITE-YML"]
    assert issues[0].severity == "warning"


def test_site_yml_schema_version_is_checked(tmp_path, write):
    write(tmp_path, "site.yml", "schema_version: 4\n")
    _, issues = load_site(tmp_path)
    assert "E-SCHEMA-VERSION" in [i.code for i in issues]


def test_site_yml_values_stay_text(tmp_path, write):
    write(tmp_path, "site.yml", "title: 1066\nhome: NO\nintro: yes\nschema_version: 2\nprivacy:\n  cutoff_years: 100\n")
    site, issues = load_site(tmp_path)
    assert issues == []
    assert site["title"] == "1066" and site["home"] == "NO" and site["intro"] == "yes"
    assert site["privacy"]["cutoff_years"] == "100" and site["schema_version"] == "2"


@pytest.mark.parametrize("version", ["4", "[1]", "abc"])
def test_a_bad_schema_version_is_an_error(tmp_path, write, version):
    write(tmp_path, "site.yml", f"schema_version: {version}\n")
    _, issues = load_site(tmp_path)
    assert [i.code for i in issues] == ["E-SCHEMA-VERSION"]


def test_duplicate_keys_in_site_yml_are_reported(tmp_path, write):
    write(tmp_path, "site.yml", "title: A\ntitle: B\n")
    site, issues = load_site(tmp_path)
    assert site["title"] == "B"
    assert [(i.code, i.path) for i in issues] == [("W-DUPLICATE-KEY", "site.yml")]


@pytest.mark.parametrize("text", ["privacy:\n\t living: hidden\n", "- a\n- b\n", "just text\n"])
def test_an_unreadable_site_yml_is_flagged(tmp_path, write, text):
    write(tmp_path, "site.yml", text)
    site, issues = load_site(tmp_path)
    assert site == {"_unreadable": True}
    assert [i.code for i in issues] == ["E-BAD-SITE-YML"]


@pytest.mark.parametrize("text", ["", "# just a comment\n", "---\n"])
def test_an_empty_site_yml_is_fine(tmp_path, write, text):
    write(tmp_path, "site.yml", text)
    assert load_site(tmp_path) == ({}, [])


def test_a_folder_with_no_family_is_an_error_that_says_how_to_start(tmp_path):
    tree, issues = load_tree(tmp_path)
    assert [i.code for i in issues if i.severity == "error"] == ["E-NO-FAMILY"]
    assert "cronicl init" in [i for i in issues if i.code == "E-NO-FAMILY"][0].message and tree.people == {}


def test_an_old_people_folder_says_to_migrate(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\n---\n")
    _, issues = load_tree(tmp_path)
    (issue,) = [i for i in issues if i.code == "E-NO-FAMILY"]
    assert "cronicl migrate" in issue.message


def test_a_syntax_error_in_site_yml_carries_the_line(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\nprivacy:\n\tliving: hidden\n")
    site, issues = load_site(tmp_path)
    assert site == {"_unreadable": True} and issues[0].line == 3 and issues[0].path == "site.yml"
