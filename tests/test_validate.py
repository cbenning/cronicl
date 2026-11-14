import pytest

from cronicl.checks import check_all as check_tree
from cronicl.core.store import load_tree
from cronicl.core.validate import is_extension, suggest


def issues_of(tmp_path, write, person_front="", site_yml=None):
    """Check a one-person family; `person_front` is extra lines of that person's record (2-space indented here)."""
    body = "".join("  " + line + "\n" for line in person_front.splitlines())
    (tmp_path / "family.yml").write_text(f"a:\n  name: {{given: Ann, surname: Lee}}\n{body}", encoding="utf-8")
    (tmp_path / "site.yml").write_text(site_yml if site_yml is not None else "title: T\nschema_version: 3\n", encoding="utf-8")
    tree, load_issues = load_tree(tmp_path)
    return check_tree(tree, load_issues)


def codes(issues):
    return sorted(i.code for i in issues)


def messages(issues, code):
    return [i.message for i in issues if i.code == code]


def test_extension_keys():
    assert all(is_extension(k) for k in ("x-foo", "X_bar", "x-"))
    assert not any(is_extension(k) for k in ("xfoo", "extra", "", "y-foo"))


def test_suggest_needs_a_close_match():
    assert suggest("birht", {"birth", "death"}) == "birth"
    assert suggest("zzzzzz", {"birth", "death"}) is None


def test_a_misspelled_person_key_is_reported_with_a_suggestion(tmp_path, write):
    found = issues_of(tmp_path, write, "birht: 1950\n")
    (msg,) = messages(found, "W-UNKNOWN-KEY")
    assert "a: unknown key 'birht'" in msg and "did you mean 'birth'?" in msg


def test_a_key_with_no_close_match_has_no_suggestion(tmp_path, write):
    (msg,) = messages(issues_of(tmp_path, write, "zzzzzzzz: 1\n"), "W-UNKNOWN-KEY")
    assert "did you mean" not in msg


@pytest.mark.parametrize(
    "front, path",
    [
        ("birth:\n  date: 1950\n  palce: X\n", "birth.palce"),
        ("death:\n  date: 1990\n  nickname: Z\n", "death.nickname"),
        ("events:\n  - type: job\n    value: x\n  - type: job\n    typo: y\n", "events[2].typo"),
        ("refs:\n  gedcom: I1\n  colour: red\n", "refs.colour"),
    ],
)
def test_unknown_keys_are_found_at_every_level(tmp_path, write, front, path):
    found = issues_of(tmp_path, write, front)
    assert any(path in m for m in messages(found, "W-UNKNOWN-KEY")), [i.message for i in found]


def test_unknown_name_keys(tmp_path, write):
    (tmp_path / "family.yml").write_text("a:\n  name:\n    given: Ann\n    maiden: Lee\n", encoding="utf-8")
    tree, load = load_tree(tmp_path)
    assert any("name.maiden" in m for m in messages(check_tree(tree, load), "W-UNKNOWN-KEY"))


@pytest.mark.parametrize(
    "front",
    [
        "x-nickname: Annie\n",
        "X_note: hi\n",
        "birth:\n  date: 1950\n  x-source: grandma\n  note: n\n  cite: c\n",
        "events:\n  - type: job\n    x-boss: Z\n",
        "refs:\n  gedcom: I1\n  x-other: 7\n",
    ],
)
def test_extension_and_known_keys_are_silent(tmp_path, write, front):
    found = issues_of(tmp_path, write, front)
    assert "W-UNKNOWN-KEY" not in codes(found), [i.message for i in found]


def test_bad_living_values(tmp_path, write):
    assert "W-LIVING-FALSE" in codes(issues_of(tmp_path, write, "living: maybe\n"))
    assert "W-LIVING-FALSE" in codes(issues_of(tmp_path, write, "living: false\n"))
    assert "W-LIVING-FALSE" not in codes(issues_of(tmp_path, write, "living: yes\n"))
    assert "W-LIVING-FALSE" not in codes(issues_of(tmp_path, write, "living: true\n"))
    assert "W-LIVING-FALSE" not in codes(issues_of(tmp_path, write, ""))


def test_site_yml_unknown_keys_with_suggestion(tmp_path, write):
    found = issues_of(tmp_path, write, site_yml="titel: X\nschema_version: 3\nprivacy:\n  livng: hidden\nx-note: ok\n")
    msgs = messages(found, "W-UNKNOWN-KEY")
    assert any("'titel'" in m and "did you mean 'title'?" in m for m in msgs)
    assert any("'privacy.livng'" in m and "did you mean 'living'?" in m for m in msgs)
    assert not any("x-note" in m for m in msgs)


@pytest.mark.parametrize(
    "site_yml, code",
    [
        ("privacy: hidden\n", "E-PRIVACY-MODE"),
        ("privacy:\n  living: nope\n", "E-PRIVACY-MODE"),
        ("privacy:\n  living:\n", "E-PRIVACY-MODE"),
        ("privacy:\n  living: hidden\n  id_salt: [x]\n", "E-PRIVACY-SALT"),
        ("privacy:\n  living: hidden\n", "W-PRIVACY-NO-SALT"),
        ("privacy:\n  living: placeholder\n  id_salt: ''\n", "W-PRIVACY-NO-SALT"),
        ("privacy:\n  cutoff_years: '100.0'\n", "W-PRIVACY-CUTOFF"),
        ("privacy:\n  cutoff_years: abc\n", "W-PRIVACY-CUTOFF"),
        ("title: [a]\n", "W-SITE-VALUE"),
        ("place_groups: Ontario\n", "W-SITE-VALUE"),
        ("place_groups:\n  Ontario: [Canada]\n", "W-PLACE-GROUPS"),
    ],
)
def test_bad_site_values(tmp_path, write, site_yml, code):
    assert code in codes(issues_of(tmp_path, write, site_yml=site_yml)), site_yml


@pytest.mark.parametrize(
    "site_yml",
    [
        "privacy:\n  living: Placeholder\n  id_salt: s\n",
        "privacy:\n  living: full\n",
        "privacy:\n  cutoff_years: ' +25 '\n",
        "title: T\nintro: hi\nhome: a\nplace_groups:\n  Ontario: Canada\n",
    ],
)
def test_valid_site_values_are_clean(tmp_path, write, site_yml):
    found = issues_of(tmp_path, write, site_yml=site_yml)
    assert not [i for i in found if i.path == "site.yml"], [i.message for i in found]


def test_redaction_off_needs_no_salt(tmp_path, write):
    assert "W-PRIVACY-NO-SALT" not in codes(issues_of(tmp_path, write, site_yml="privacy:\n  living: full\n"))


def test_gallery_extension_keys_exempt_only_from_the_unknown_key_warning(tmp_path, write):
    found = issues_of(tmp_path, write, site_yml="gallery:\n  type: fussel\n  url: https://x.example/\n  x-note: hi\n  x-token: abc\n")
    assert "W-GALLERY-KEY" not in codes(found)
    assert codes(found).count("W-GALLERY-SECRET") == 1


def test_a_rule_that_raises_is_reported_for_that_person_only(tmp_path, write, monkeypatch):
    (tmp_path / "family.yml").write_text(
        "a:\n  name: {given: A, surname: One}\nb:\n  name: {given: B, surname: Two}\n  birth: 19x0\n", encoding="utf-8"
    )
    tree, load = load_tree(tmp_path)
    real = __import__("cronicl.core.check", fromlist=["x"])._check_person

    def boom(person, out):
        if person.id == "a":
            raise RuntimeError("kaput")
        return real(person, out)

    monkeypatch.setattr("cronicl.core.check._check_person", boom)
    found = check_tree(tree, load)
    (v,) = [i for i in found if i.code == "E-VALIDATOR"]
    assert "a: validation failed: kaput" in v.message and v.path == "family.yml"
    assert "W-DATE-UNPARSED" in codes(found)


def test_a_whole_tree_step_that_raises_is_reported_without_a_file(tmp_path, write, monkeypatch):
    (tmp_path / "family.yml").write_text("a:\n  name: {given: A, surname: One}\n", encoding="utf-8")
    tree, load = load_tree(tmp_path)

    def boom(_tree):
        raise RuntimeError("no relations")

    monkeypatch.setattr("cronicl.core.check.build_relations", boom)
    found = check_tree(tree, load)
    (v,) = [i for i in found if i.code == "E-VALIDATOR"]
    assert "relations" in v.message and "no relations" in v.message and v.path is None
