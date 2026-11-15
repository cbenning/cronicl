"""The map page in headless Chrome against a local tile server. Skipped when node or a browser is absent."""
import base64
import functools
import http.server
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from test_browser_smoke import find_chrome

from cronicl.cli import main

ROOT = Path(__file__).parent
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


class TileHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG)))
        self.end_headers()
        self.wfile.write(PNG)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(find_chrome() is None, reason="no headless Chrome found (set CRONICL_CHROME)")
def test_the_map_in_a_real_browser(tmp_path):
    tile_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TileHandler)
    threading.Thread(target=tile_server.serve_forever, daemon=True).start()
    tiles = f"http://127.0.0.1:{tile_server.server_address[1]}"
    data, out = tmp_path / "fam", tmp_path / "out"
    assert main(["init", "--dir", str(data)]) == 0
    (data / "family.yml").write_text(
        "ada:\n  name: {given: Ada, surname: Lovelace}\n  birth: {date: 1815, place: \"London, England\"}\n"
        "  death: {date: 1852, place: \"Ockham, Surrey\"}\n"
        "bob:\n  name: {given: Bob, surname: Smith}\n  birth: {date: 1900, place: \"London, England\"}\n",
        encoding="utf-8",
    )
    (data / "site.yml").write_text(
        "title: T\nschema_version: 3\nplaces:\n  \"London, England\": [51.5072, -0.1276]\n  \"Ockham, Surrey\": [51.2900, -0.4400]\n"
        f"map:\n  type: osm\n  tiles: {tiles}/{{z}}/{{x}}/{{y}}.png\n  attribution: Test tiles\n",
        encoding="utf-8",
    )
    assert main(["build", "--dir", str(data), "--out", str(out)]) == 0
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    handler.log_message = lambda *args, **kwargs: None
    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            ["node", str(ROOT / "browser" / "map.mjs"), find_chrome(), f"http://127.0.0.1:{site.server_address[1]}", tiles,
             str(tmp_path / "shots")],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        site.shutdown()
        tile_server.shutdown()
    assert result.returncode == 0, result.stdout + result.stderr
