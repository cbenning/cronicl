import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from famsite.render import build_site

ROOT = Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_viewer_js_unit_tests():
    files = [str(ROOT / "js" / name) for name in ("culling.test.js", "viewer-helpers.test.js", "site.test.js")]
    result = subprocess.run(["node", "--test", *files], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_viewer_assets_are_copied_into_the_build(tmp_path, make_tree):
    build_site(make_tree([{"id": "a", "given": "A"}]), tmp_path, today=date(2026, 10, 10))
    assert (tmp_path / "viewer.js").exists()
    assert (tmp_path / "style.css").exists()
