"""Click-through test of a built site in headless Chrome. Skipped when node or a browser is absent.

Set CRONICL_CHROME to a Chrome/Chromium/chrome-headless-shell binary to choose one explicitly.
"""
import base64
import functools
import glob
import http.server
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cronicl.cli import main

ROOT = Path(__file__).parent


def find_chrome() -> str | None:
    explicit = os.environ.get("CRONICL_CHROME")
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
@pytest.mark.skipif(find_chrome() is None, reason="no headless Chrome found (set CRONICL_CHROME)")
def test_viewer_in_a_real_browser(tmp_path, sample_ged):
    data = tmp_path / "fam"
    out = tmp_path / "out"
    assert main(["init", "--dir", str(data)]) == 0
    assert main(["import-gedcom", str(sample_ged), "--dir", str(data), "-a"]) == 0
    (data / "media").mkdir(exist_ok=True)
    (data / "media" / "maude.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
    )
    with (data / "family.yml").open("a", encoding="utf-8") as family:
        family.write(
            "\nellsworth-maude:\n  name: {given: Maude Sylvie Marnie, surname: Ellsworth}\n"
            "  birth: 1925\n  death: 1990\n  portrait: maude.png\n  parents: [smith-john, brown-mary]\n"
            "  events:\n    - {type: occupation, value: Teacher, date: 1950}\n"
            "\nkid-now:\n  name: {given: Kid, surname: Now}\n  birth: 2000-05-05\n  parents: [smith-bob]\n"
            "\nold-open:\n  name: {given: Old, surname: Open}\n  birth: 1850\n"
            "\nlong-date:\n  name: {given: Long, surname: Date}\n  birth: 1941-09-30\n  death: 1999-12-28\n"
            "\nlone-person:\n  name: {given: Lone, surname: Person}\n"
            "\nwife-first:\n  name: {given: Ex, surname: Wife}\n"
            "\nsmith-john + wife-first:\n  events:\n    - {type: marriage, date: 1940}\n"
            "    - {type: divorce, date: 1945}\n"
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
