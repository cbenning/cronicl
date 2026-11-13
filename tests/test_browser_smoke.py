"""Click-through test of a built site in headless Chrome. Skipped when node or a browser is absent.

Set FAMSITE_CHROME to a Chrome/Chromium/chrome-headless-shell binary to choose one explicitly.
"""
import functools
import glob
import http.server
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from famsite.cli import main

ROOT = Path(__file__).parent


def find_chrome() -> str | None:
    explicit = os.environ.get("FAMSITE_CHROME")
    if explicit:
        return explicit
    pattern = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")
    for candidate in sorted(glob.glob(pattern)):
        return candidate
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(find_chrome() is None, reason="no headless Chrome found (set FAMSITE_CHROME)")
def test_viewer_in_a_real_browser(tmp_path, sample_ged):
    data = tmp_path / "fam"
    out = tmp_path / "out"
    assert main(["init", "--dir", str(data)]) == 0
    assert main(["import-gedcom", str(sample_ged), "--dir", str(data), "-a"]) == 0
    (data / "people" / "ellsworth-maude.md").write_text(
        "---\nid: ellsworth-maude\nname:\n  given: Maude Sylvie Marnie\n  surname: Ellsworth\n"
        "birth: 1925\ndeath: 1990\nparents: [smith-john, brown-mary]\n---\n",
        encoding="utf-8",
    )
    (data / "people" / "kid-now.md").write_text(
        "---\nid: kid-now\nname:\n  given: Kid\n  surname: Now\nbirth: 2000-05-05\nparents: [smith-bob]\n---\n",
        encoding="utf-8",
    )
    (data / "people" / "old-open.md").write_text(
        "---\nid: old-open\nname:\n  given: Old\n  surname: Open\nbirth: 1850\n---\n", encoding="utf-8"
    )
    (data / "people" / "lone-person.md").write_text(
        "---\nid: lone-person\nname:\n  given: Lone\n  surname: Person\n---\n", encoding="utf-8"
    )
    (data / "people" / "wife-first.md").write_text(
        "---\nid: wife-first\nname:\n  given: Ex\n  surname: Wife\n"
        "partnerships:\n  - with: smith-john\n    type: marriage\n    start: 1940\n    end: 1945\n"
        "    end_reason: divorce\n---\n",
        encoding="utf-8",
    )
    assert main(["build", "--dir", str(data), "--out", str(out)]) == 0

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    handler.log_message = lambda *args, **kwargs: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        result = subprocess.run(
            ["node", str(ROOT / "browser" / "smoke.mjs"), find_chrome(), url, str(tmp_path / "shots")],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stdout + result.stderr
