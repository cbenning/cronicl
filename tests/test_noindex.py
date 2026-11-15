"""site.yml `noindex: true`: robots meta in every page, robots.txt and _headers; cleanup only of what cronicl wrote."""
from datetime import date

from cronicl.cli import main
from cronicl.site.render import build_site

TODAY = date(2026, 10, 10)
MARK = "# written by cronicl (noindex: true)"


def tree_with(make_tree, site):
    tree = make_tree([{"id": "a", "given": "A", "surname": "One"}, {"id": "b", "given": "B", "parents": ["a"]}])
    tree.site = site
    return tree


def pages(out):
    return sorted(out.rglob("*.html"))


def test_noindex_adds_the_robots_meta_to_every_page_and_writes_robots_txt_and_headers(tmp_path, make_tree):
    build_site(tree_with(make_tree, {"noindex": "true"}), tmp_path, today=TODAY)
    found = pages(tmp_path)
    assert len(found) >= 8
    for page in found:
        assert '<meta name="robots" content="noindex, nofollow">' in page.read_text(encoding="utf-8"), page
    robots = (tmp_path / "robots.txt").read_text(encoding="utf-8")
    assert robots.startswith(MARK) and "User-agent: *" in robots and "Disallow: /" in robots
    headers = (tmp_path / "_headers").read_text(encoding="utf-8")
    assert headers.startswith(MARK) and "/*\n  X-Robots-Tag: noindex, nofollow" in headers


def test_default_build_has_no_robots_meta_and_no_extra_files(tmp_path, make_tree):
    build_site(tree_with(make_tree, {}), tmp_path, today=TODAY)
    assert not (tmp_path / "robots.txt").exists() and not (tmp_path / "_headers").exists()
    assert all("robots" not in page.read_text(encoding="utf-8") for page in pages(tmp_path))


def test_turning_noindex_off_removes_only_the_files_cronicl_wrote(tmp_path, make_tree):
    build_site(tree_with(make_tree, {"noindex": "yes"}), tmp_path, today=TODAY)
    build_site(tree_with(make_tree, {}), tmp_path, today=TODAY)
    assert not (tmp_path / "robots.txt").exists() and not (tmp_path / "_headers").exists()
    assert all("robots" not in page.read_text(encoding="utf-8") for page in pages(tmp_path))


def test_a_hand_written_robots_txt_is_never_touched_and_is_reported(tmp_path, make_tree):
    (tmp_path / "robots.txt").write_text("User-agent: Googlebot\nAllow: /\n", encoding="utf-8")
    (tmp_path / "_headers").write_text("/*\n  X-Frame-Options: DENY\n", encoding="utf-8")
    summary = build_site(tree_with(make_tree, {"noindex": "true"}), tmp_path, today=TODAY)
    assert (tmp_path / "robots.txt").read_text(encoding="utf-8").startswith("User-agent: Googlebot")
    assert (tmp_path / "_headers").read_text(encoding="utf-8").startswith("/*\n  X-Frame")
    assert len(summary.notes) == 2 and all("W-NOINDEX-FILE" in n for n in summary.notes)
    build_site(tree_with(make_tree, {}), tmp_path, today=TODAY)
    assert (tmp_path / "robots.txt").exists() and (tmp_path / "_headers").exists()


def test_an_unreadable_noindex_value_is_reported_and_counts_as_off(tmp_path, write_family, capsys):
    write_family(tmp_path, "a:\n  name: {given: A}\n")
    (tmp_path / "site.yml").write_text("schema_version: 3\nnoindex: maybe\n", encoding="utf-8")
    assert main(["check", "--dir", str(tmp_path)]) == 0
    assert "W-SITE-VALUE" in capsys.readouterr().out
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert not (tmp_path / "out" / "robots.txt").exists()


def test_the_cli_build_prints_the_hand_written_file_warning(tmp_path, write_family, capsys):
    write_family(tmp_path, "a:\n  name: {given: A}\n")
    (tmp_path / "site.yml").write_text("schema_version: 3\nnoindex: true\n", encoding="utf-8")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "robots.txt").write_text("mine\n", encoding="utf-8")
    capsys.readouterr()
    assert main(["build", "--dir", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert "W-NOINDEX-FILE" in capsys.readouterr().out
