"""Nothing an author types may make `check` or `build` raise: every input ends in issues or a site."""
import pytest

from cronicl.cli import main


def run(*argv):
    return main([str(a) for a in argv])


GOOD_PERSON = "a:\n  name: {given: Ann, surname: Lee}\n  birth: 1950\n  bio: Bio.\n"

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
    "empty-file": "",
    "comments-only": "# nothing here\n",
    "list-file": "- a\n- b\n",
    "text-file": "just a bio\n",
    "blank-record": "a:\n",
    "record-text": "a: hello\n",
    "record-list": "a: [x, y]\n",
    "name-text": "a:\n  name: Bob Smith\n",
    "name-list": "a:\n  name: [a, b]\n",
    "name-map-list": "a:\n  name:\n    given: [a]\n",
    "name-blank": "a:\n  name: {given: '   '}\n",
    "birth-list": "a:\n  name: {given: A}\n  birth: [1950]\n",
    "birth-map-list": "a:\n  name: {given: A}\n  birth:\n    date:\n      x: y\n",
    "death-garbage": "a:\n  name: {given: A}\n  death: when the wind blew\n",
    "events-text": "a:\n  name: {given: A}\n  events: hello\n",
    "events-strings": "a:\n  name: {given: A}\n  events: [a, b]\n",
    "events-nested": "a:\n  name: {given: A}\n  events: [[a], [b]]\n",
    "parents-map": "a:\n  name: {given: A}\n  parents:\n    a: b\n",
    "parents-text": "a:\n  name: {given: A}\n  parents: smith\n",
    "parents-self": "a:\n  name: {given: A}\n  parents: [a]\n",
    "parents-too-many": "a:\n  name: {given: A}\n  parents: [a, b, c]\nb:\n  name: {given: B}\nc:\n  name: {given: C}\n",
    "living-maybe": "a:\n  name: {given: A}\n  living: maybe\n",
    "living-blank": "a:\n  name: {given: A}\n  living:\n",
    "living-list": "a:\n  name: {given: A}\n  living: [a]\n",
    "sex-word": "a:\n  name: {given: A}\n  sex: woman\n",
    "sex-list": "a:\n  name: {given: A}\n  sex: [male]\n",
    "unknown-keys": "a:\n  name: {given: A}\n  birht: 1\n  name2: x\n  birth:\n    palce: x\n",
    "dup-keys": "a:\n  name: {given: A}\n  birth: 1\n  birth: 2\n",
    "dup-records": "a:\n  name: {given: A}\na:\n  name: {given: B}\n",
    "bad-key": "Not A Key:\n  name: {given: A}\n",
    "couple-self": "a + a: {}\n",
    "couple-dangling": "a:\n  name: {given: A}\na + ghost: {}\n",
    "couple-three": "a + b + c: {}\n",
    "couple-garbage-events": "a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  events: [[marriage]]\n",
    "couple-note-list": "a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  note: [x]\n",
    "couple-dates": "a:\n  name: {given: A}\nb:\n  name: {given: B}\na + b:\n  events:\n    - {type: marriage, date: nonsense}\n    - {type: divorce, date: FROM 1 TO 2}\n",
    "unicode-name": "a:\n  name: {given: 太郎, surname: 山田}\n",
    "emoji-name": "a:\n  name: {given: 🌳, surname: Tree}\n",
    "huge-bio": "a:\n  name: {given: A}\n  bio: |\n" + "".join(f"    lorem ipsum dolor {n}\n" for n in range(30000)),
    "refs-list": "a:\n  name: {given: A}\n  refs: [a]\n",
    "portrait-list": "a:\n  name: {given: A}\n  portrait: [a]\n",
    "portrait-escape": "a:\n  name: {given: A}\n  portrait: ../../etc/passwd\n",
    "tab-indent": "a:\n\tname: {given: A}\n",
    "complex-key-list": "[note]: hello\n",
    "complex-key-map": "{a: b}: c\n",
    "merge-key": "base: &b\n  name: {given: X}\na:\n  <<: *b\n",
    "comma-trap": "a:\n  name: {given: A}\n  birth: {date: 1850, place: London, England}\n",
    "unclosed-flow": "a:\n  name: {given: A\n",
    "binary": "a:\n  name: \x00\x01\n",
}


def make(tmp_path, write, site=None, person=GOOD_PERSON):
    data = tmp_path / "data"
    assert run("init", "--dir", data) == 0
    if site is not None:
        write(data, "site.yml", site)
    write(data, "family.yml", person)
    return data


def check_and_build(tmp_path, data):
    checked = run("check", "--dir", data)
    built = run("build", "--dir", data, "--out", tmp_path / "out")
    assert checked in (0, 1, 2) and built in (0, 1, 2)
    if checked == 0:
        assert built == 0 and (tmp_path / "out" / "index.html").exists()
    assert run("check", "--dir", data, "--format", "json") in (0, 1, 2)


@pytest.mark.parametrize("name", sorted(SITES))
def test_odd_site_yml_never_raises(tmp_path, write, name):
    check_and_build(tmp_path, make(tmp_path, write, site=SITES[name]))


@pytest.mark.parametrize("name", sorted(PEOPLE))
def test_odd_person_files_never_raise(tmp_path, write, name):
    check_and_build(tmp_path, make(tmp_path, write, person=PEOPLE[name]))
