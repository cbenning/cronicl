"""One consistent way to say where the cronicl folder is, and what 'write' means."""
import pytest

from cronicl.cli import main
from cronicl.store import load_tree


def repo(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\nschema_version: 1\n")
    write(tmp_path, "people/bob.md", "---\nid: smith-bob\nname: Bob Smith\n---\n")
    return tmp_path


def test_dir_is_accepted_after_and_before_the_subcommand_and_as_c(tmp_path, write):
    repo(tmp_path, write)
    assert main(["check", "--dir", str(tmp_path)]) == 0
    assert main(["--dir", str(tmp_path), "check"]) == 0
    assert main(["check", "-C", str(tmp_path)]) == 0
    assert main(["-C", str(tmp_path), "check", "--strict"]) == 1  # filename drift warning


def test_every_state_command_takes_dir(tmp_path, write):
    repo(tmp_path, write)
    ged = tmp_path / "t.ged"
    ged.write_text("0 HEAD\n0 @I1@ INDI\n1 NAME A /B/\n0 TRLR\n", encoding="utf-8")
    assert main(["fix", "--dir", str(tmp_path)]) == 0
    assert main(["search", "bob", "--dir", str(tmp_path)]) == 0
    assert main(["import-gedcom", str(ged), "--dir", str(tmp_path)]) == 0  # dry run
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert main(["edit", "mark-living", "smith-bob", "--dir", str(tmp_path)]) == 0


def test_environment_variable_is_the_fallback_and_the_flag_wins(tmp_path, write, monkeypatch):
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    repo(good, write)
    write(bad, "site.yml", "title: T\nschema_version: 1\n")
    write(bad, "people/x.md", "---\nid: x\nname: X\nparents: [ghost]\n---\n")
    monkeypatch.setenv("CRONICL_DIR", str(bad))
    assert main(["check"]) == 1  # env points at the broken repo
    assert main(["check", "--dir", str(good)]) == 0  # flag beats env


def test_default_is_the_current_directory(tmp_path, write, monkeypatch):
    repo(tmp_path, write)
    monkeypatch.delenv("CRONICL_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 0


def test_positional_dir_and_into_are_gone(tmp_path, write):
    repo(tmp_path, write)
    with pytest.raises(SystemExit) as exc:
        main(["check", str(tmp_path)])
    assert exc.value.code == 2
    ged = tmp_path / "t.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["import-gedcom", str(ged), "--into", str(tmp_path)])
    assert exc.value.code == 2


def test_edit_previews_by_default_and_writes_with_apply_or_a(tmp_path, write, capsys):
    repo(tmp_path, write)
    path = tmp_path / "people/bob.md"
    before = path.read_bytes()
    capsys.readouterr()
    assert main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "would set living: false" in out and "--apply" in out
    assert path.read_bytes() == before
    assert main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path), "-a"]) == 0
    tree, _ = load_tree(tmp_path)
    assert tree.people["smith-bob"].living is False


def test_dry_run_flag_is_gone(tmp_path, write):
    repo(tmp_path, write)
    with pytest.raises(SystemExit):
        main(["edit", "mark-deceased", "smith-bob", "--dir", str(tmp_path), "--dry-run"])


def test_apply_has_the_same_short_form_on_every_writer(tmp_path, write):
    repo(tmp_path, write)
    assert main(["fix", "--dir", str(tmp_path), "-a"]) == 0
    assert (tmp_path / "people" / "smith-bob.md").exists()
    ged = tmp_path / "t.ged"
    ged.write_text("0 HEAD\n0 @I1@ INDI\n1 NAME A /B/\n0 TRLR\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    assert main(["import-gedcom", str(ged), "--dir", str(other), "-a"]) == 0
    assert (other / "people" / "b-a.md").exists()


def test_force_is_split_into_allow_dirty_and_ignore_errors(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\nschema_version: 1\n")
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\nparents: [ghost]\n---\n")
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "o1")]) == 1
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "o2"), "--ignore-errors"]) == 0
    for argv in (["build", "--dir", str(tmp_path), "--force"], ["fix", "--dir", str(tmp_path), "--force"]):
        with pytest.raises(SystemExit):
            main(argv)
    assert main(["fix", "--dir", str(tmp_path), "--allow-dirty"]) == 0
