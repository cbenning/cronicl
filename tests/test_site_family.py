import importlib

import pytest

from cronicl.core.search import search_people
from cronicl.core.store import load_tree
from cronicl.site.links import page_links, valid_edit_url
from cronicl.site.render import build_site, life_summary

from datetime import date

TODAY = date(2026, 10, 10)

FAMILY = """\
alder-ada:
  name: {given: Ada, surname: Alder, nickname: Addie, also: [Ada King, Countess of Lovelace]}
  birth: {date: BET 1880 AND 1890, place: "Leeds, England"}
  death: {date: 1950}
alder-walt:
  name: {prefix: Dr, given: Walt, surname: Alder, suffix: Jr}
  birth: 1850
  death: 1920
alder-ada + alder-walt:
  events:
    - {type: marriage, date: 1905}
old-maybe:
  name: {given: Old, surname: Maybe}
  birth: AFT 1920
mid-maybe:
  name: {given: Mid, surname: Maybe}
  birth: BET 1700 AND 1750
gone-unknown:
  name: {given: Gone, surname: Unknown}
  birth: 1900
  death: unknown
"""


def load(tmp_path, write_family, extra_site=""):
    write_family(tmp_path, FAMILY)
    if extra_site:
        (tmp_path / "site.yml").write_text("title: T\nschema_version: 3\n" + extra_site, encoding="utf-8")
    tree, issues = load_tree(tmp_path)
    assert [i for i in issues if i.severity == "error"] == [], issues
    return tree


def page(tmp_path, pid):
    return (tmp_path / "out" / "p" / pid / "index.html").read_text(encoding="utf-8")


def test_the_home_page_has_no_recently_updated_and_history_is_gone(tmp_path, write_family):
    tree = load(tmp_path, write_family)
    build_site(tree, tmp_path / "out", today=TODAY)
    home = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "recent" not in home.lower()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("cronicl.site.history")


def test_the_build_does_not_run_git(tmp_path, write_family, monkeypatch):
    import subprocess

    calls = []
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or real(*a, **k))
    from cronicl.cli import main

    write_family(tmp_path, FAMILY)
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert not [c for c in calls if c and "git" in str(c[0])[:20]]


@pytest.mark.parametrize(
    "template, ok",
    [
        ("https://github.com/x/y/blob/main/{file}#L{line}", True),
        ("https://example.org/edit/{id}", True),
        ("https://example.org/{file}", False),
        ("https://example.org/none", False),
        ("javascript:alert({id})", False),
        (5, False),
    ],
)
def test_edit_url_needs_an_id_or_a_line(template, ok):
    assert valid_edit_url(template) is ok


def test_edit_links_use_the_file_and_line_of_the_record():
    site = {"edit_url": "https://github.com/x/y/blob/main/{file}#L{line}"}
    assert page_links(site, "alder-ada", "Ada", source="family.yml", line=17) == [
        {"href": "https://github.com/x/y/blob/main/family.yml#L17", "text": "Edit this page"}
    ]
    assert page_links(site, "a", "A", source="family/two.yml", line=3)[0]["href"].endswith("family/two.yml#L3")
    assert page_links(site, "a", "A") == []  # a person with no file and line gets no link
    assert page_links({"edit_url": "https://x.example/{id}"}, "alder-ada", "A")[0]["href"] == "https://x.example/alder-ada"


def test_person_pages_carry_the_edit_link_with_the_line(tmp_path, write_family):
    tree = load(tmp_path, write_family, "edit_url: https://github.com/x/y/blob/main/{file}#L{line}\n")
    build_site(tree, tmp_path / "out", today=TODAY)
    line = tree.people["alder-ada"].line
    assert f'href="https://github.com/x/y/blob/main/family.yml#L{line}"' in page(tmp_path, "alder-ada")


def test_other_names_show_on_the_page_and_are_searchable(tmp_path, write_family):
    tree = load(tmp_path, write_family)
    build_site(tree, tmp_path / "out", today=TODAY)
    html = page(tmp_path, "alder-ada")
    assert "Also known as" in html and "Addie" in html and "Ada King" in html and "Countess of Lovelace" in html
    for query in ("addie", "countess", "king"):
        assert "alder-ada" in [h.id for h in search_people(tree, query, today=TODAY)]


def test_prefix_and_suffix_are_part_of_the_displayed_name(tmp_path, write_family):
    tree = load(tmp_path, write_family)
    assert tree.people["alder-walt"].display_name == "Dr Walt Alder Jr"
    build_site(tree, tmp_path / "out", today=TODAY)
    assert "<h1>Dr Walt Alder Jr</h1>" in page(tmp_path, "alder-walt")


def test_qualified_dates_read_in_words_on_the_page(tmp_path, write_family):
    tree = load(tmp_path, write_family)
    build_site(tree, tmp_path / "out", today=TODAY)
    assert "Born between 1880 and 1890" in page(tmp_path, "alder-ada")


def test_a_death_of_unknown_date_reads_naturally():
    payload = {"birth": {"when": "1900", "place": None, "date": "1900"}, "death": {"when": "date unknown", "place": None, "date": "unknown"}}
    assert life_summary(payload) == "Born 1900. Died."
    payload["death"]["place"] = "Leeds"
    assert life_summary(payload) == "Born 1900. Died in Leeds."


def test_placeholder_privacy_treats_uncertain_birth_dates_as_possibly_living(tmp_path, write_family):
    tree = load(tmp_path, write_family, "privacy:\n  living: placeholder\n  id_salt: s\n")
    build_site(tree, tmp_path / "out", today=TODAY)
    everything = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "out").rglob("*.json"))
    assert "Old Maybe" not in everything and "old-maybe" not in everything  # AFT 1920, no death: may be alive
    assert "Mid Maybe" in everything  # BET 1700 AND 1750: long dead by any reading
    assert "Gone Unknown" in everything  # death: unknown means deceased
    assert "Ada Alder" in everything


def test_the_search_finds_people_with_unknown_death_dates(tmp_path, write_family):
    tree = load(tmp_path, write_family)
    (hit,) = [h for h in search_people(tree, "gone", today=TODAY) if h.id == "gone-unknown"]
    assert hit.living is False
