import json

import pytest

from cronicl.cli import main
from cronicl.core.store import load_tree


def run(*argv):
    return main([str(a) for a in argv])


BASE = (
    "alder-walter:\n  name: {given: Walter, surname: Alder}\n  birth: 1835\n"
    "alder-ada:\n  name: {given: Ada, surname: Alder}\n  birth: 1840\n  death: 1912\n"
    "alder-ada + alder-walter:\n  events:\n    - {type: marriage, date: 1862-06-14}\n"
    "alder-ben:\n  name: {given: Ben, surname: Alder}\n  birth: 1864\n  parents: [alder-walter, alder-ada]\n"
    "alder-cora:\n  name: {given: Cora, surname: Alder}\n  birth: 1866\n  parents: [alder-walter, alder-ada]\n"
)


def test_init_makes_a_clean_family_folder(tmp_path, capsys):
    assert run("init", "--dir", tmp_path) == 0
    site = (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert "schema_version: 3" in site and "living: full" in site
    import re

    assert re.search(r"id_salt: [0-9a-f]{16}", site)
    family = (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert family.lstrip().startswith("#") and "alder" not in family.split("#")[0]
    assert (tmp_path / "media").is_dir() and (tmp_path / "archive").is_dir() and not (tmp_path / "people").exists()
    assert run("check", "--dir", tmp_path) == 0 and capsys.readouterr().out.strip().count("ERROR") == 0
    assert run("build", "--dir", tmp_path, "--out", tmp_path / "out") == 0
    assert run("init", "--dir", tmp_path) == 2


def test_the_example_in_the_init_comments_is_valid_yaml_when_uncommented(tmp_path):
    from cronicl.core.yamltext import load_text

    run("init", "--dir", tmp_path)
    lines = (tmp_path / "family.yml").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("# lovelace-ada:"))
    end = next(i for i in range(start, len(lines)) if lines[i] == "#" and lines[i + 1].startswith("# Add people"))
    example = "\n".join(line[2:] if line.startswith("# ") else "" for line in lines[start:end])
    result = load_text(example)
    assert result.error is None and list(result.data) == ["lovelace-ada", "king-william + lovelace-ada"]
    tree, issues = load_tree(tmp_path)
    assert tree.people == {} and [i for i in issues if i.severity == "error"] == []


def test_new_previews_then_appends_only(tmp_path, write_family, capsys):
    path = write_family(tmp_path, "# my family\n\n" + BASE)
    before = path.read_bytes()
    assert run("new", "--dir", tmp_path, "--given", "Dan", "--surname", "Alder", "--birth", "1892-08-20", "--birth-place", "Leeds, England", "--parents", "alder-walter", "alder-ada") == 0
    out = capsys.readouterr().out
    assert "alder-dan:" in out and "dry run" in out and path.read_bytes() == before
    assert run("new", "--dir", tmp_path, "--given", "Dan", "--surname", "Alder", "--birth", "1892-08-20", "--birth-place", "Leeds, England", "--parents", "alder-walter", "alder-ada", "--apply") == 0
    after = path.read_bytes()
    assert after.startswith(before) and after != before
    tree, issues = load_tree(tmp_path)
    dan = tree.people["alder-dan"]
    assert (dan.given, dan.birth.place, dan.parents) == ("Dan", "Leeds, England", ["alder-walter", "alder-ada"])
    assert [i for i in issues if i.severity == "error"] == []


def test_new_respects_crlf_and_a_missing_final_newline(tmp_path, write_family):
    path = write_family(tmp_path, BASE.replace("\n", "\r\n").rstrip("\r\n"))
    run("new", "--dir", tmp_path, "--given", "Eli", "--apply")
    raw = path.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert "alder-" not in raw.decode().split("eli:")[0].split("\r\n")[-1]
    tree, _ = load_tree(tmp_path)
    assert "eli" in tree.people


def test_new_ids_are_unique_and_explicit_ids_are_checked(tmp_path, write_family, capsys):
    write_family(tmp_path, BASE)
    run("new", "--dir", tmp_path, "--given", "Ben", "--surname", "Alder", "--apply")
    tree, _ = load_tree(tmp_path)
    assert "alder-ben-2" in tree.people
    assert run("new", "--dir", tmp_path, "--given", "X", "--id", "alder-ben", "--apply") == 2
    assert run("new", "--dir", tmp_path, "--given", "X", "--id", "Bad Id", "--apply") == 2
    assert run("new", "--dir", tmp_path, "--apply") == 2  # no name
    assert run("new", "--dir", tmp_path, "--given", "X", "--parents", "ghost", "--apply") == 2
    assert run("new", "--dir", tmp_path, "--given", "X", "--birth", "nonsense", "--apply") == 2
    assert run("new", "--dir", tmp_path, "--given", "X", "--parents", "alder-ada", "alder-ada", "--apply") == 2


def test_new_partner_appends_an_empty_couple_record(tmp_path, write_family):
    write_family(tmp_path, BASE)
    run("new", "--dir", tmp_path, "--given", "Fay", "--surname", "Alder", "--sex", "female", "--partner", "alder-ben", "--apply")
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert "alder-ben + alder-fay: {}" in text and "sex: female" in text
    tree, issues = load_tree(tmp_path)
    assert "alder-fay" in tree.people["alder-ben"].spouse or tree.people["alder-ben"].spouse == ["alder-fay"]


def test_new_in_a_split_family_needs_a_file(tmp_path, write_family):
    write_family(tmp_path, BASE, "family/one.yml")
    assert run("new", "--dir", tmp_path, "--given", "X", "--apply") == 2
    assert run("new", "--dir", tmp_path, "--given", "X", "--file", "two.yml", "--apply") == 0
    assert (tmp_path / "family" / "two.yml").exists()
    tree, _ = load_tree(tmp_path)
    assert tree.people["x"].source == "family/two.yml"


def test_new_with_the_death_word_unknown(tmp_path, write_family):
    write_family(tmp_path, BASE)
    assert run("new", "--dir", tmp_path, "--given", "Old", "--death", "unknown", "--apply") == 0
    assert "death: unknown" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_show_describes_a_person_as_the_site_sees_them(tmp_path, write_family, capsys):
    write_family(tmp_path, BASE)
    capsys.readouterr()
    assert run("show", "alder-ben", "--dir", tmp_path) == 0
    out = capsys.readouterr().out
    assert "Ben Alder (alder-ben)" in out and "family.yml:" in out
    assert "Walter Alder (alder-walter)" in out and "Ada Alder (alder-ada)" in out
    assert "Cora Alder (alder-cora)" in out  # sibling
    capsys.readouterr()
    run("show", "alder-ada", "--dir", tmp_path)
    out = capsys.readouterr().out
    assert "married" in out.lower() and "1862-06-14" in out and "Ben Alder" in out and "Cora Alder" in out


def test_show_an_unknown_id_is_an_error(tmp_path, write_family, capsys):
    write_family(tmp_path, BASE)
    assert run("show", "nobody", "--dir", tmp_path) == 2
    assert "nobody" in capsys.readouterr().err
