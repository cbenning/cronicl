import json
import re
from pathlib import Path

from cronicl.cli import main


def run(*argv):
    return main([str(a) for a in argv])


def tree_files(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_init_creates_a_data_repo_and_refuses_to_overwrite(tmp_path):
    assert run("init", "--dir", tmp_path) == 0
    site = (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert "schema_version: 2" in site
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
    for rel in ("index.html", "tree/index.html", "timeline/index.html", "layout.json", "index.json", "viewer.js", "style.css", "p/smith-bob/index.html"):
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
    assert {"parents", "spouse", "children", "partnerships"} <= set(props)


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


def test_serve_sends_no_cache_headers_so_a_rebuilt_viewer_is_never_stale(tmp_path):
    import functools
    import threading
    import urllib.request

    from cronicl.cli import NoCacheHandler, make_server

    (tmp_path / "viewer.js").write_text("console.log(1)", encoding="utf-8")
    server = make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/viewer.js") as response:
            assert "no-cache" in response.headers["Cache-Control"]
    finally:
        server.shutdown()
        server.server_close()
    assert issubclass(NoCacheHandler, __import__("http.server").server.SimpleHTTPRequestHandler)
    assert server.allow_reuse_address  # restarting serve must not hit "Address already in use"


def test_build_warns_when_living_people_are_published(tmp_path, write, capsys):
    root = tmp_path / "fam"
    assert main(["init", "--dir", str(root)]) == 0
    write(root, "people/kid.md", "---\nname:\n  given: Kid\nbirth: 1990\n---\n")
    write(root, "people/old.md", "---\nname:\n  given: Old\nbirth: 1800\n---\n")
    assert main(["build", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "W-PRIVACY-OFF" in out and "1 person is treated as living" in out


def test_build_is_quiet_when_redaction_is_on(tmp_path, write, capsys):
    root = tmp_path / "fam"
    assert main(["init", "--dir", str(root)]) == 0
    site = root / "site.yml"
    site.write_text(site.read_text().replace("living: full", "living: placeholder"))
    write(root, "people/kid.md", "---\nname:\n  given: Kid\nbirth: 1990\n---\n")
    assert main(["build", "--dir", str(root)]) == 0
    assert "W-PRIVACY-OFF" not in capsys.readouterr().out


def test_init_creates_media_folder(tmp_path):
    assert main(["init", "--dir", str(tmp_path / "fam")]) == 0
    assert (tmp_path / "fam" / "media" / ".gitkeep").exists()


def test_build_refuses_to_write_over_the_data_folder(tmp_path, write):
    root = tmp_path / "fam"
    assert main(["init", "--dir", str(root)]) == 0
    write(root, "people/a.md", "---\nname: A\n---\n")
    (root / "media").mkdir(exist_ok=True)
    (root / "media" / "keep.jpg").write_bytes(b"x")
    assert main(["build", "--dir", str(root), "--out", str(root)]) == 2
    assert (root / "people" / "a.md").exists() and (root / "media" / "keep.jpg").exists()
    assert main(["build", "--dir", str(root), "--out", str(root / "people")]) == 2
    assert (root / "people" / "a.md").exists()


def _site_with_a_living_person(tmp_path, write, site_yml):
    data = tmp_path / "data"
    run("init", "--dir", data)
    write(data, "site.yml", site_yml)
    write(data, "people/kid.md", "---\nid: kid\nname:\n  given: Secretname\n  surname: Livingperson\nbirth: 2020\n---\n")
    return data


def _everything(out: Path) -> str:
    return "".join(p.read_text(encoding="utf-8", errors="ignore") for p in out.rglob("*") if p.is_file() and p.suffix in (".html", ".json"))


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "site_yml",
    [
        "schema_version: 2\nprivacy:\n  living: nope\n",
        "schema_version: 2\nprivacy: hidden\n",
        "schema_version: 2\nprivacy:\n  living:\n",
        "schema_version: 2\nprivacy:\n\tliving: hidden\n",  # tab: unreadable
        "- a\n- b\n",
    ],
)
def test_a_broken_privacy_setting_fails_closed_even_when_errors_are_ignored(tmp_path, write, site_yml):
    data = _site_with_a_living_person(tmp_path, write, site_yml)
    assert run("build", "--dir", data, "--out", tmp_path / "out", "--ignore-errors") == 0
    assert "Secretname" not in _everything(tmp_path / "out")
    assert not (tmp_path / "out" / "p" / "kid").exists()  # nor the real id


def test_a_bad_cutoff_does_not_crash_the_build(tmp_path, write):
    data = _site_with_a_living_person(tmp_path, write, "schema_version: 2\nprivacy:\n  living: placeholder\n  cutoff_years: abc\n")
    assert run("build", "--dir", data, "--out", tmp_path / "out") == 0
    assert "Secretname" not in _everything(tmp_path / "out")


def test_mode_words_and_text_numbers_in_site_yml_work(tmp_path, write):
    data = _site_with_a_living_person(tmp_path, write, "schema_version: 2\nprivacy:\n  living: Placeholder\n  cutoff_years: '25'\n  id_salt: s\n")
    assert run("build", "--dir", data, "--out", tmp_path / "out") == 0
    assert "Secretname" not in _everything(tmp_path / "out")


def test_warning_summary_formats():
    from cronicl.cli import warning_summary
    from cronicl.core.issues import Issue

    assert warning_summary([]) == ""
    assert warning_summary([Issue("W-A", "x")]) == "1 warning: 1 W-A (run cronicl check for details)"
    many = [Issue("W-UNKNOWN-KEY", "x")] * 3 + [Issue("W-BAD-LIVING", "x")] + [Issue(f"W-C{n}", "x") for n in range(5)]
    text = warning_summary(many)
    assert text.startswith("9 warnings: 3 W-UNKNOWN-KEY, 1 W-BAD-LIVING, 1 W-C0, 1 W-C1, 1 W-C2, ... (run cronicl check for details)")


def test_build_prints_one_summary_line_for_warnings(tmp_path, write, capsys):
    data = tmp_path / "data"
    run("init", "--dir", data)
    write(data, "people/a.md", "---\nid: a\nname: Ann Lee\nbirht: 1950\nlivng: no\nliving: maybe\n---\n")
    capsys.readouterr()
    assert run("build", "--dir", data, "--out", tmp_path / "out") == 0
    out = capsys.readouterr().out
    assert "3 warnings: 2 W-UNKNOWN-KEY, 1 W-BAD-LIVING (run cronicl check for details)" in out
    assert "did you mean" not in out and "unknown key" not in out


def test_build_prints_errors_in_full_and_stops(tmp_path, write, capsys):
    data = tmp_path / "data"
    run("init", "--dir", data)
    write(data, "people/a.md", "---\nid: a\nname: Ann Lee\nparents: [ghost]\n---\n")
    capsys.readouterr()
    assert run("build", "--dir", data, "--out", tmp_path / "out") == 1
    assert "E-DANGLING-REF" in capsys.readouterr().out


def test_validate_is_an_alias_for_check(tmp_path, write, capsys):
    data = tmp_path / "data"
    run("init", "--dir", data)
    write(data, "people/a.md", "---\nid: a\nname: Ann Lee\nbirht: 1950\n---\n")
    capsys.readouterr()
    code_check = run("check", "--dir", data, "--format", "json")
    first = capsys.readouterr().out
    code_validate = run("validate", "--dir", data, "--format", "json")
    assert capsys.readouterr().out == first and code_check == code_validate == 0
    assert run("validate", "--dir", data, "--strict") == 1


def test_a_merge_key_in_site_yml_fails_closed(tmp_path, write, capsys):
    data = _site_with_a_living_person(
        tmp_path, write, "schema_version: 2\nbase: &b\n  living: hidden\n  id_salt: s\nprivacy:\n  <<: *b\n"
    )
    assert run("check", "--dir", data) == 1
    assert "E-BAD-SITE-YML" in capsys.readouterr().out
    assert run("build", "--dir", data, "--out", tmp_path / "out", "--ignore-errors") == 0
    assert "Secretname" not in _everything(tmp_path / "out") and not (tmp_path / "out" / "p" / "kid").exists()


@pytest.mark.parametrize("site_yml", ["schema_version: 2\nplace_groups:\n  [a]: x\n", "schema_version: 2\n? [a, b]\n: y\n"])
def test_a_list_used_as_a_key_is_an_error_not_a_crash(tmp_path, write, capsys, site_yml):
    data = _site_with_a_living_person(tmp_path, write, site_yml)
    assert run("check", "--dir", data) == 1
    assert "E-BAD-SITE-YML" in capsys.readouterr().out
    assert run("build", "--dir", data, "--out", tmp_path / "out", "--ignore-errors") == 0
    assert "Secretname" not in _everything(tmp_path / "out")


def test_a_list_used_as_a_key_in_a_person_file_is_an_error(tmp_path, write, capsys):
    data = tmp_path / "data"
    run("init", "--dir", data)
    write(data, "people/a.md", "---\nname: A\n[note]: hello\n---\n")
    capsys.readouterr()
    assert run("check", "--dir", data) == 1
    assert "E-BAD-FRONTMATTER" in capsys.readouterr().out


def test_ignoring_errors_says_what_was_ignored(tmp_path, write, capsys):
    data = _site_with_a_living_person(tmp_path, write, "schema_version: 2\nprivacy: hidden\n")
    capsys.readouterr()
    assert run("build", "--dir", data, "--out", tmp_path / "out", "--ignore-errors") == 0
    out = capsys.readouterr().out
    assert "ignoring 1 error: 1 E-PRIVACY-MODE (run cronicl check for details)" in out
    assert "living people are treated as placeholders" in out


def test_a_text_cutoff_really_applies(tmp_path, write):
    from datetime import date

    born = date.today().year - 30
    person = f"---\nid: mid\nname:\n  given: Midlife\n  surname: Person\nbirth: {born}\n---\n"
    for cutoff, shown in (("25", True), ("100", False)):
        data = tmp_path / f"data{cutoff}"
        run("init", "--dir", data)
        write(data, "site.yml", f"schema_version: 2\nprivacy:\n  living: placeholder\n  cutoff_years: '{cutoff}'\n  id_salt: s\n")
        write(data, "people/mid.md", person)
        assert run("build", "--dir", data, "--out", tmp_path / f"out{cutoff}") == 0
        assert ("Midlife" in _everything(tmp_path / f"out{cutoff}")) is shown, cutoff
