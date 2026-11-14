import random
import re

import pytest

from cronicl.cli import main
from cronicl.core.inplace import InplaceError, rename, set_death_unknown, set_living
from cronicl.core.store import load_tree

DOC = """\
# the Alder line -- keep this comment
smith:
  name: {given: Sam, surname: Smith}   # trailing comment mentioning smith
  bio: |
    smith appears here and so does smith-john in the story.

smith-john:
  name: {given: John, surname: Smith}
  parents: [smith, "smith-ann"]

smith-ann:
  name:
    given: Ann
    surname: Smith
  parents:
    - smith
    - 'smith-john'

smith + smith-ann:
  events:
    - {type: marriage, date: 1900}

smith-john + smith-ann: {}
"quoted":
  name: {given: Q}
"""


def test_rename_touches_only_the_scalars_that_are_the_id():
    new, count = rename(DOC, "smith", "smyth")
    lines_old, lines_new = DOC.split("\n"), new.split("\n")
    changed = [i for i, (a, b) in enumerate(zip(lines_old, lines_new)) if a != b]
    assert len(lines_old) == len(lines_new) and count == 4
    assert "smyth:" in new and "# trailing comment mentioning smith" in new
    assert "smith appears here and so does smith-john in the story." in new  # a bio is never touched
    assert "parents: [smyth, \"smith-ann\"]" in new and "    - smyth\n" in new
    assert "smyth + smith-ann:" in new and "smith-john + smith-ann: {}" in new
    assert "smith-john:" in new and "smith-ann:" in new  # ids that merely start with the old one
    assert [lines_old[i] for i in range(len(lines_old)) if i not in changed] == [lines_new[i] for i in range(len(lines_new)) if i not in changed]


def test_rename_keeps_quotes_and_second_halves():
    text = 'a:\n  name: {given: A}\n"b":\n  parents: ["a"]\nc + a: {}\na + "b": {}\n'
    new, count = rename(text, "a", "z")
    assert new == 'z:\n  name: {given: A}\n"b":\n  parents: ["z"]\nc + z: {}\nz + "b": {}\n' and count == 4


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("final", [True, False])
@pytest.mark.parametrize("bom", [True, False])
def test_rename_survives_line_endings_bom_and_a_missing_final_newline(newline, final, bom):
    text = DOC.replace("\n", newline)
    text = text if final else text.rstrip("\r\n")
    text = ("\ufeff" if bom else "") + text
    new, count = rename(text, "smith-ann", "smith-anne")
    assert count == 4 and new.replace("smith-anne", "smith-ann") == text
    assert new.startswith("\ufeff") is bom and new.endswith(newline) is final


def test_rename_counts_zero_for_an_unknown_id_and_refuses_unreadable_text():
    assert rename(DOC, "nobody", "x") == (DOC, 0)
    with pytest.raises(InplaceError):
        rename("a:\n\tb: 1\n", "a", "z")


def test_random_renames_never_change_a_byte_outside_the_touched_ids():
    rng = random.Random(3)
    ids = ["smith", "smith-john", "smith-ann", "quoted"]
    for _ in range(200):
        old, new_id = rng.choice(ids), f"x{rng.randint(1, 99)}"
        new, count = rename(DOC, old, new_id)
        assert count > 0 and new != DOC
        assert len(new.splitlines()) == len(DOC.splitlines())
        assert new.replace(new_id, old) == DOC  # undoing the renamed ids gives back every other byte


def test_set_death_unknown_goes_after_birth_and_is_idempotent():
    text = "a:\n  name: {given: A}\n  birth: 1850\n  parents: [b]\n\nb:\n  name: {given: B}\n"
    new = set_death_unknown(text, "a")
    assert new == "a:\n  name: {given: A}\n  birth: 1850\n  death: unknown\n  parents: [b]\n\nb:\n  name: {given: B}\n"
    assert set_death_unknown(new, "a") == new


def test_set_death_unknown_without_birth_block_birth_and_blank_records():
    assert set_death_unknown("a:\n  name: {given: A}\n", "a") == "a:\n  name: {given: A}\n  death: unknown\n"
    block = "a:\n  birth:\n    date: 1850\n    place: X\n  parents: [b]\n"
    assert set_death_unknown(block, "a") == "a:\n  birth:\n    date: 1850\n    place: X\n  death: unknown\n  parents: [b]\n"
    assert set_death_unknown("a:\n", "a") == "a:\n  death: unknown\n"
    crlf = "a:\r\n  birth: 1850\r\n"
    assert set_death_unknown(crlf, "a") == "a:\r\n  birth: 1850\r\n  death: unknown\r\n"


def test_set_death_unknown_leaves_a_person_who_has_a_death_alone():
    text = "a:\n  death: 1900\n"
    assert set_death_unknown(text, "a") == text


def test_set_living_inserts_or_replaces():
    assert set_living("a:\n  name: {given: A}\n", "a") == "a:\n  name: {given: A}\n  living: true\n"
    assert set_living("a:\n  living: false\n  name: {given: A}\n", "a") == "a:\n  living: true\n  name: {given: A}\n"
    assert set_living("a:\n  living: true\n", "a") == "a:\n  living: true\n"


def test_edits_refuse_what_they_cannot_do_in_place():
    with pytest.raises(InplaceError):
        set_death_unknown("a: {name: {given: A}}\n", "a")
    with pytest.raises(InplaceError):
        set_death_unknown("a:\n  name: {given: A}\n", "nobody")


def run(*argv):
    return main([str(a) for a in argv])


FAMILY = DOC.replace('"quoted":\n  name: {given: Q}\n', "")


def test_rename_command_previews_then_applies_across_files_and_home(tmp_path, write_family, capsys):
    write_family(tmp_path, FAMILY)
    (tmp_path / "site.yml").write_text("title: T\nschema_version: 3\nhome: smith  # the root\n", encoding="utf-8")
    before = (tmp_path / "family.yml").read_bytes()
    assert run("rename", "smith", "smyth", "--dir", tmp_path) == 0
    assert "dry run" in capsys.readouterr().out and (tmp_path / "family.yml").read_bytes() == before
    assert run("rename", "smith", "smyth", "--dir", tmp_path, "--apply") == 0
    tree, issues = load_tree(tmp_path)
    assert "smyth" in tree.people and "smith" not in tree.people and tree.people["smith-john"].parents == ["smyth", "smith-ann"]
    assert tree.site["home"] == "smyth" and "# the root" in (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert [i for i in issues if i.severity == "error"] == []


def test_rename_command_refuses_bad_requests(tmp_path, write_family):
    write_family(tmp_path, FAMILY)
    assert run("rename", "smith", "smith-john", "--dir", tmp_path, "--apply") == 2
    assert run("rename", "smith", "Bad Id", "--dir", tmp_path, "--apply") == 2
    assert run("rename", "nobody", "x", "--dir", tmp_path, "--apply") == 2
    assert run("rename", "smith", "smith", "--dir", tmp_path, "--apply") == 2


def test_rename_command_in_a_split_family(tmp_path, write_family):
    write_family(tmp_path, "a:\n  name: {given: A}\n", "family/one.yml")
    write_family(tmp_path, "b:\n  name: {given: B}\n  parents: [a]\n", "family/two.yml")
    assert run("rename", "a", "z", "--dir", tmp_path, "--apply") == 0
    assert (tmp_path / "family/one.yml").read_text(encoding="utf-8").startswith("z:")
    assert "parents: [z]" in (tmp_path / "family/two.yml").read_text(encoding="utf-8")


def test_edit_mark_commands_on_a_family_file(tmp_path, write_family, capsys):
    write_family(tmp_path, "a:\n  name: {given: A}\n  birth: 1850\nb:\n  name: {given: B}\n  death: 1900\n")
    assert run("edit", "mark-deceased", "a", "b", "--dir", tmp_path) == 0
    out = capsys.readouterr().out
    assert "would set death: unknown" in out and "unchanged" in out and "dry run" in out
    assert "death: unknown" not in (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert run("edit", "mark-deceased", "a", "b", "--dir", tmp_path, "--apply") == 0
    assert (tmp_path / "family.yml").read_text(encoding="utf-8").count("death:") == 2
    assert run("edit", "mark-living", "a", "--dir", tmp_path, "--apply") == 0
    assert "living: true" in (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert run("edit", "mark-living", "nobody", "--dir", tmp_path, "--apply") == 2
