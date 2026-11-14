"""The gallery block in headless Chrome against a stub gallery on another port (so every fetch is cross-origin)."""
import base64
import functools
import http.server
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from test_browser_smoke import find_chrome

from famsite.cli import main

ROOT = Path(__file__).parent
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _photo(n):
    return {"name": f"p{n}.jpg", "thumb": f"static/_gallery/albums/trip/p{n}.jpg", "url": f"#/collections/people/jane-doe/p{n}"}


def _manifest(photos, version=1):
    return {
        "version": version,
        "people": [
            {"name": "Jane Doe", "slug": "jane-doe", "url": "#/collections/people/jane-doe", "count": 12, "thumb": None, "photos": photos}
        ],
    }


EVIL = [
    {"name": "evil1", "thumb": "https://evil.invalid/x.png", "url": "#/collections/people/jane-doe/e1"},
    {"name": "evil2", "thumb": "//evil.invalid/x.png", "url": "#/collections/people/jane-doe/e2"},
    {"name": "evil3", "thumb": "../x.png", "url": "#/collections/people/jane-doe/e3"},
]


def _gallery_server(state, stop):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

        def _send(self, code, body, ctype, cors=True):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if cors:
                self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.startswith("/__mode/"):
                state["mode"] = path[len("/__mode/"):]
                return self._send(200, b"ok", "text/plain")
            if path == "/photos/people.json":
                mode = state["mode"]
                if mode == "hang":
                    stop.wait(30)
                    return
                if mode == "notfound":
                    return self._send(404, b"nope", "text/plain")
                if mode == "badjson":
                    return self._send(200, b"<html>not json</html>", "text/html")
                if mode == "hostile":
                    body = _manifest([_photo(1)] + EVIL)
                elif mode == "badversion":
                    body = _manifest([_photo(1)], version=2)
                else:
                    body = _manifest([_photo(n) for n in range(1, 9)])
                return self._send(200, json.dumps(body).encode(), "application/json", cors=mode != "nocors")
            if path.endswith((".png", ".jpg")):
                return self._send(200, PNG, "image/png", cors=False)
            self._send(404, b"", "text/plain")

    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(find_chrome() is None, reason="no headless Chrome found (set FAMSITE_CHROME)")
def test_gallery_in_a_real_browser(tmp_path):
    stop = threading.Event()
    gallery = _gallery_server({"mode": "ok"}, stop)
    threading.Thread(target=gallery.serve_forever, daemon=True).start()
    gallery_base = f"http://127.0.0.1:{gallery.server_address[1]}"

    data, out = tmp_path / "fam", tmp_path / "out"
    assert main(["init", "--dir", str(data)]) == 0
    (data / "site.yml").write_text(
        "title: T\nschema_version: 2\nprivacy:\n  living: placeholder\n  cutoff_years: 100\n"
        f"gallery:\n  type: fussel\n  label: Family photos\n  url: {gallery_base}/photos\n",
        encoding="utf-8",
    )
    people = {
        "jane-doe": "name:\n  given: Jane\n  surname: Doe\nbirth: 1950\ndeath: 2010\n",
        "lone-person": "name:\n  given: Lone\n  surname: Person\nbirth: 1940\ndeath: 2000\n",
        "living-kid": "name:\n  given: Kid\n  surname: Now\nbirth: 2020\n",
    }
    for pid, front in people.items():
        (data / "people" / f"{pid}.md").write_text(f"---\nid: {pid}\n{front}---\n", encoding="utf-8")
    assert main(["build", "--dir", str(data), "--out", str(out)]) == 0

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    handler.log_message = lambda *args, **kwargs: None
    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            ["node", str(ROOT / "browser" / "gallery.mjs"), find_chrome(), f"http://127.0.0.1:{site.server_address[1]}",
             gallery_base, str(tmp_path / "shots")],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        stop.set()
        site.shutdown()
        gallery.shutdown()
    assert result.returncode == 0, result.stdout + result.stderr
