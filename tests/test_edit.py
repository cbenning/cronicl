import pytest

from cronicl.cli import main
from cronicl.edit import EditError, apply_living, set_living_in_text
from cronicl.store import load_tree


def test_replaces_an_existing_living_line():
    text = "---\nid: a\nliving: true\nname: A\n---\nBody\n"
    assert set_living_in_text(text, False) == "---\nid: a\nliving: false\nname: A\n---\nBody\n"


def test_appends_inside_the_frontmatter_when_absent():
    text = "---\nid: a\nname: A\n---\nBody\n"
    assert set_living_in_text(text, False) == "---\nid: a\nname: A\nliving: false\n---\nBody\n"


def test_creates_frontmatter_when_the_file_has_none():
    assert set_living_in_text("Just a bio\n", False) == "---\nliving: false\n---\nJust a bio\n"


def test_preserves_crlf_line_endings():
    text = "---\r\nid: a\r\nname: A\r\n---\r\nBody\r\n"
    out = set_living_in_text(text, True)
    assert out == "---\r\nid: a\r\nname: A\r\nliving: true\r\n---\r\nBody\r\n"


def test_ignores_indented_living_inside_a_block_scalar():
    text = "---\nid: a\ngedcom_extra: |-\n  living: true\n---\n"
    out = set_living_in_text(text, False)
    assert "  living: true" in out
    assert out.count("living: false") == 1


def test_is_idempotent_and_preserves_comments():
    text = "---\n# keep me\nid: a   # trailing\nname:\n  given: A\n---\nBody\n"
    once = set_living_in_text(text, False)
    assert "# keep me" in once and "id: a   # trailing" in once
    assert set_living_in_text(once, False) == once


def make_repo(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\nschema_version: 1\n")
    write(tmp_path, "people/smith-bob.md", "---\nid: smith-bob\nname: Bob Smith\n# note\n---\nBio\n")
    write(tmp_path, "people/smith-amy.md", "---\nid: smith-amy\nname: Amy Smith\n---\n")
    write(tmp_path, "people/other.md", "---\nid: other\nname: Other Person\n---\n")


def test_apply_living_edits_only_the_named_files(tmp_path, write):
    make_repo(tmp_path, write)
    before_other = (tmp_path / "people/other.md").read_bytes()
    changes = apply_living(tmp_path, ["smith-bob", "smith-amy"], False)
    assert {path.name for path, changed in changes if changed} == {"smith-bob.md", "smith-amy.md"}
    tree, _ = load_tree(tmp_path)
    assert tree.people["smith-bob"].living is False and tree.people["smith-amy"].living is False
    assert tree.people["other"].living is None
    assert (tmp_path / "people/other.md").read_bytes() == before_other
    assert "# note" in (tmp_path / "people/smith-bob.md").read_text(encoding="utf-8")


def test_unknown_id_aborts_before_any_write(tmp_path, write):
    make_repo(tmp_path, write)
    before = (tmp_path / "people/smith-bob.md").read_bytes()
    with pytest.raises(EditError, match="ghost"):
        apply_living(tmp_path, ["smith-bob", "ghost"], False)
    assert (tmp_path / "people/smith-bob.md").read_bytes() == before


def test_dry_run_writes_nothing(tmp_path, write):
    make_repo(tmp_path, write)
    before = (tmp_path / "people/smith-bob.md").read_bytes()
    changes = apply_living(tmp_path, ["smith-bob"], False, dry_run=True)
    assert [changed for _, changed in changes] == [True]
    assert (tmp_path / "people/smith-bob.md").read_bytes() == before


def test_cli_mark_deceased_and_mark_living(tmp_path, write, capsys):
    make_repo(tmp_path, write)
    assert main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path), "--apply"]) == 0
    assert "smith-bob.md" in capsys.readouterr().out
    tree, _ = load_tree(tmp_path)
    assert tree.people["smith-bob"].living is False
    assert main(["edit", "mark-living", "smith-bob", "-C", str(tmp_path), "-a"]) == 0
    tree, _ = load_tree(tmp_path)
    assert tree.people["smith-bob"].living is True


def test_cli_unknown_id_exits_2_and_changes_nothing(tmp_path, write, capsys):
    make_repo(tmp_path, write)
    before = (tmp_path / "people/smith-bob.md").read_bytes()
    assert main(["edit", "mark-deceased", "smith-bob", "ghost", "--dir", str(tmp_path), "--apply"]) == 2
    assert "ghost" in capsys.readouterr().err
    assert (tmp_path / "people/smith-bob.md").read_bytes() == before


def test_cli_unchanged_files_are_reported(tmp_path, write, capsys):
    make_repo(tmp_path, write)
    main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path), "--apply"])
    capsys.readouterr()
    assert main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path), "--apply"]) == 0
    assert "unchanged" in capsys.readouterr().out
