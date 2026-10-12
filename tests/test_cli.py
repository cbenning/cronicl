import json
import re
from pathlib import Path

from famsite.cli import main


def run(*argv):
    return main([str(a) for a in argv])


def tree_files(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_init_creates_a_data_repo_and_refuses_to_overwrite(tmp_path):
    assert run("init", "--dir", tmp_path) == 0
    site = (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert "schema_version: 1" in site
    assert re.search(r"id_salt: [0-9a-f]{16}", site)
    assert "living: full" in site  # redaction is opt-in
    assert (tmp_path / "people").is_dir() and (tmp_path / "archive").is_dir()
    assert not (tmp_path / "unions").exists()
    assert run("init", "--dir", tmp_path) == 2


def test_check_exit_codes_and_json(tmp_path, write, capsys):
    run("init", "--dir", tmp_path)
    write(tmp_path, "people/bob.md", "---\nid: smith-bob\nname: Bob Smith\nparents: [ghost]\n---\n")
    capsys.readouterr()
    assert run("check", "--dir", tmp_path, "--format", "json") == 1
    out = json.loads(capsys.readouterr().out)
    assert {i["code"] for i in out} >= {"E-DANGLING-REF", "W-FILENAME-DRIFT"}
    assert all({"code", "severity", "message", "path"} <= set(i) for i in out)


def test_check_warnings_only_pass_unless_strict(tmp_path, write):
    run("init", "--dir", tmp_path)
    write(tmp_path, "people/bob.md", "---\nid: smith-bob\nname: Bob Smith\n---\n")
    assert run("check", "--dir", tmp_path) == 0
    assert run("check", "--dir", tmp_path, "--strict") == 1


def test_fix_dry_run_then_apply(tmp_path, write):
    run("init", "--dir", tmp_path)
    write(tmp_path, "people/bob.md", "---\nid: smith-bob\nname: Bob Smith\n---\n")
    assert run("fix", "--dir", tmp_path) == 0
    assert (tmp_path / "people" / "bob.md").exists()
    assert run("fix", "--dir", tmp_path, "--apply") == 0
    assert (tmp_path / "people" / "smith-bob.md").exists()
    assert not (tmp_path / "people" / "bob.md").exists()


def test_import_dry_run_writes_nothing(tmp_path, sample_ged, capsys):
    run("init", "--dir", tmp_path)
    before = tree_files(tmp_path)
    capsys.readouterr()
    assert run("import-gedcom", sample_ged, "--dir", tmp_path) == 0
    assert tree_files(tmp_path) == before
    out = capsys.readouterr().out
    assert "8 people" in out and "2 families" in out


def test_import_rejects_ansel_with_exit_2(tmp_path):
    run("init", "--dir", tmp_path)
    bad = tmp_path / "bad.ged"
    bad.write_bytes(b"0 HEAD\n1 CHAR ANSEL\n")
    assert run("import-gedcom", bad, "--dir", tmp_path, "--apply") == 2


def test_end_to_end_import_check_build(tmp_path, sample_ged):
    data = tmp_path / "data"
    out = tmp_path / "out"
    run("init", "--dir", data)
    site = data / "site.yml"
    site.write_text(site.read_text(encoding="utf-8").replace("living: full", "living: placeholder"), encoding="utf-8")
    assert run("import-gedcom", sample_ged, "--dir", data, "--apply") == 0
    assert any((data / "archive").glob("sample-*.ged"))
    assert run("check", "--dir", data) == 0
    assert run("build", "--dir", data, "--out", out) == 0
    for rel in ("index.html", "layout.json", "index.json", "viewer.js", "style.css", "p/smith-bob/index.html"):
        assert (out / rel).exists(), rel
    # Privacy: Jane (born ~1952, no death) and Tom (born 2012) are living and must not appear.
    for rel, data_bytes in tree_files(out).items():
        text = data_bytes.decode("utf-8", errors="ignore")
        assert not re.search(r"\bJane\b|\bJones\b|\bTom\b", text), rel
        assert "jones-jane" not in text and "smith-tom" not in text, rel


def test_build_is_deterministic_end_to_end(tmp_path, sample_ged):
    data = tmp_path / "data"
    run("init", "--dir", data)
    run("import-gedcom", sample_ged, "--dir", data, "--apply")
    run("build", "--dir", data, "--out", tmp_path / "a")
    run("build", "--dir", data, "--out", tmp_path / "b")
    assert tree_files(tmp_path / "a") == tree_files(tmp_path / "b")


def test_a_person_added_by_one_new_file_appears_in_the_build(tmp_path, sample_ged, write):
    data = tmp_path / "data"
    run("init", "--dir", data)
    run("import-gedcom", sample_ged, "--dir", data, "--apply")
    # One new file: a new ancestor declared only by a down-reference to an existing person.
    write(
        data,
        "people/smith-henry.md",
        "---\nname: Henry Smith\nbirth: 1890\ndeath: 1960\nchildren: [smith-john]\n---\nFather of John.\n",
    )
    assert run("check", "--dir", data) == 0
    assert run("build", "--dir", data, "--out", tmp_path / "out") == 0
    payload = json.loads((tmp_path / "out" / "data/people/smith-john.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in payload["parents"]] == ["smith-henry"]


def test_build_refuses_when_check_has_errors(tmp_path, write):
    # Review focus 5: a cycle must block the build, not hang it.
    run("init", "--dir", tmp_path)
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\nparents:\n  - a\n---\n")
    assert run("build", "--dir", tmp_path, "--out", tmp_path / "out") == 1
    assert not (tmp_path / "out" / "index.html").exists()


def test_schema_prints_valid_json(capsys):
    assert run("schema") == 0
    schema = json.loads(capsys.readouterr().out)
    assert set(schema) == {"person"}
    props = schema["person"]["properties"]
    assert {"parents", "spouse", "children", "marriages"} <= set(props)


def test_build_does_not_redact_unless_asked(tmp_path, sample_ged):
    data = tmp_path / "data"
    run("init", "--dir", data)  # init writes privacy.living: full
    run("import-gedcom", sample_ged, "--dir", data, "--apply")
    run("build", "--dir", data, "--out", tmp_path / "out")
    index = (tmp_path / "out" / "index.json").read_text(encoding="utf-8")
    assert "Jane Jones" in index and "Tom Smith" in index and "Living" not in index


def test_build_with_no_privacy_key_does_not_redact(tmp_path, sample_ged, write):
    data = tmp_path / "data"
    write(data, "site.yml", "title: T\nschema_version: 1\n")
    run("import-gedcom", sample_ged, "--dir", data, "--apply")
    run("build", "--dir", data, "--out", tmp_path / "out")
    assert "Jane Jones" in (tmp_path / "out" / "index.json").read_text(encoding="utf-8")
