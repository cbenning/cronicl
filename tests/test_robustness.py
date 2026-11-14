"""Nothing an author types may make `check` or `build` raise: every input ends in issues or a site."""
import pytest

from cronicl.cli import main


def run(*argv):
    return main([str(a) for a in argv])


GOOD_PERSON = "---\nid: a\nname: Ann Lee\nbirth: 1950\n---\nBio.\n"

SITES = {
    "empty": "",
    "comment": "# nothing\n",
    "list": "- a\n- b\n",
    "text": "just text\n",
    "tabs": "privacy:\n\tliving: hidden\n",
    "dup": "title: A\ntitle: B\n",
    "privacy-blank": "privacy:\n",
    "privacy-string": "privacy: hidden\n",
    "privacy-list": "privacy: [a]\n",
    "living-nope": "privacy:\n  living: nope\n",
    "living-blank": "privacy:\n  living:\n",
    "living-caps": "privacy:\n  living: HIDDEN\n",
    "cutoff-abc": "privacy:\n  living: placeholder\n  cutoff_years: abc\n",
    "cutoff-neg": "privacy:\n  cutoff_years: -1\n",
    "cutoff-huge": "privacy:\n  cutoff_years: 1e9\n",
    "cutoff-blank": "privacy:\n  cutoff_years: ''\n",
    "salt-list": "privacy:\n  living: hidden\n  id_salt: [x]\n",
    "title-list": "title: [a]\n",
    "intro-map": "intro:\n  a: 1\n",
    "home-list": "home: [a]\n",
    "place-groups-text": "place_groups: x\n",
    "place-groups-list-value": "place_groups:\n  Ontario: [Canada]\n",
    "gallery-text": "gallery: x\n",
    "gallery-bad": "gallery:\n  type: fussel\n  url: 5\n  portraits: maybe\n",
    "version-list": "schema_version: [1]\n",
    "unicode": "title: Familie Müller 🌳\nintro: 日本語\n",
    "complex-key-list": "place_groups:\n  [a]: x\n",
    "complex-key-explicit": "? [a, b]\n: y\n",
    "complex-key-map": "{a: b}: c\n",
    "merge-key": "base: &b\n  living: hidden\n  id_salt: s\nprivacy:\n  <<: *b\n",
    "alias-whole-block": "p: &p\n  living: hidden\n  id_salt: s\nprivacy: *p\n",
}

PEOPLE = {
    "empty-front": "---\n---\n",
    "front-list": "---\n- a\n---\n",
    "no-front": "just a bio\n",
    "name-list": "---\nname: [a, b]\n---\n",
    "name-map-list": "---\nname:\n  given: [a]\n---\n",
    "birth-list": "---\nname: A\nbirth: [1950]\n---\n",
    "death-map": "---\nname: A\ndeath:\n  date:\n    x: y\n---\n",
    "events-string": "---\nname: A\nevents: hello\n---\n",
    "events-list-of-strings": "---\nname: A\nevents: [a, b]\n---\n",
    "partnerships-bad": "---\nname: A\npartnerships: [a]\n---\n",
    "parents-map": "---\nname: A\nparents:\n  a: b\n---\n",
    "living-maybe": "---\nname: A\nliving: maybe\n---\n",
    "living-blank": "---\nname: A\nliving:\n---\n",
    "living-list": "---\nname: A\nliving: [a]\n---\n",
    "sex-word": "---\nname: A\nsex: female\n---\n",
    "unknown-keys": "---\nname: A\nbirht: 1\nname2: x\nbirth:\n  palce: x\n---\n",
    "dup-keys": "---\nname: A\nbirth: 1\nbirth: 2\n---\n",
    "blank-name": "---\nname: '   '\n---\n",
    "id-spaces": "---\nid: has spaces\nname: A\n---\n",
    "id-emoji": "---\nid: 🌳\nname: A\n---\n",
    "unicode-name": "---\nname: 山田 太郎\n---\n",
    "emoji-name": "---\nname: 🌳 Tree\n---\n",
    "huge-body": "---\nname: A\n---\n" + ("lorem ipsum " * 90000),
    "gallery-id-list": "---\nname: A\ngallery_id: [a]\n---\n",
    "portrait-list": "---\nname: A\nportrait: [a]\n---\n",
    "tab-indent": "---\nname:\n\tgiven: A\n---\n",
    "complex-key-list": "---\nname: A\n[note]: hello\n---\n",
    "complex-key-map": "---\nname: A\n{a: b}: c\n---\n",
    "merge-key": "---\nbase: &b\n  given: X\nname:\n  <<: *b\n---\n",
}


def make(tmp_path, write, site=None, person=GOOD_PERSON):
    data = tmp_path / "data"
    assert run("init", "--dir", data) == 0
    if site is not None:
        write(data, "site.yml", site)
    write(data, "people/a.md", person)
    return data


def check_and_build(tmp_path, data):
    checked = run("check", "--dir", data)
    built = run("build", "--dir", data, "--out", tmp_path / "out")
    assert checked in (0, 1, 2) and built in (0, 1, 2)
    if checked == 0:
        assert built == 0 and (tmp_path / "out" / "index.html").exists()


@pytest.mark.parametrize("name", sorted(SITES))
def test_odd_site_yml_never_raises(tmp_path, write, name):
    check_and_build(tmp_path, make(tmp_path, write, site=SITES[name]))


@pytest.mark.parametrize("name", sorted(PEOPLE))
def test_odd_person_files_never_raise(tmp_path, write, name):
    check_and_build(tmp_path, make(tmp_path, write, person=PEOPLE[name]))
