"""The project is called cronicl: package, command, env var, page markers and storage keys."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_and_command_are_cronicl():
    import cronicl.cli

    assert cronicl.cli.main(["schema"]) == 0


def test_no_source_file_still_says_famsite():
    offenders = []
    for path in (ROOT / "src").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".js", ".html", ".css"):
            if re.search("famsite", path.read_text(encoding="utf-8"), re.I):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_built_pages_carry_the_new_names(tmp_path, make_tree):
    from datetime import date

    from cronicl.render import build_site

    build_site(make_tree([{"id": "a", "given": "A"}]), tmp_path, today=date(2026, 10, 10))
    page = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    assert "cronicl-root" in page and "famsite" not in page.lower()
