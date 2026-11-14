"""The gallery block in headless Chrome against a stub gallery on another port (so every fetch is cross-origin)."""
import base64
import functools
import http.server
import json
import shutil
import struct
import subprocess
import threading
import zlib
from pathlib import Path

import pytest
from test_browser_smoke import find_chrome

from cronicl.cli import main

ROOT = Path(__file__).parent
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _png(width, height, rgb=(180, 90, 140)):
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


TALL = _png(30, 40)  # a portrait photo: real aspect ratios are what break layouts


def _photo(n):
    return {
        "name": f"p{n}.jpg",
        "thumb": f"static/_gallery/albums/trip/p{n}.jpg",
        "src": f"static/_gallery/albums/trip/big{n}.jpg",
        "url": f"#/collections/people/jane-doe/p{n}",
    }


FACE = "static/_gallery/albums/trip/face-jane.jpg"


def _manifest(photos, version=1, face=FACE):
    john = [{**_photo(n), "url": f"#/collections/people/john-doe/p{n}"} for n in (1, 2, 3)]
    return {
        "version": version,
        "people": [
            {"name": "Jane Doe", "slug": "jane-doe", "url": "#/collections/people/jane-doe", "count": 12, "thumb": face, "photos": photos},
            {"name": "John Doe", "slug": "john-doe", "url": "#/collections/people/john-doe", "count": 3,
             "thumb": "static/_gallery/albums/trip/face-john.jpg", "photos": john},
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
                    body = _manifest([{**_photo(1), "src": "https://evil.invalid/big.jpg"}] + EVIL, face="https://evil.invalid/face.png")
                elif mode == "badsrc":
                    body = _manifest([{**_photo(n), "src": f"static/_gallery/albums/trip/missing{n}.jpg"} for n in range(1, 9)])
                elif mode == "nosrc":
                    body = _manifest([{k: v for k, v in _photo(n).items() if k != "src"} for n in range(1, 9)], face=None)
                elif mode == "badversion":
                    body = _manifest([_photo(1)], version=2)
                else:
                    body = _manifest([_photo(n) for n in range(1, 9)])
                return self._send(200, json.dumps(body).encode(), "application/json", cors=mode != "nocors")
            if "missing" in path:
                return self._send(404, b"", "text/plain", cors=False)
            if path.endswith((".png", ".jpg")):
                return self._send(200, TALL, "image/png", cors=False)
            self._send(404, b"", "text/plain")

    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(find_chrome() is None, reason="no headless Chrome found (set CRONICL_CHROME)")
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
        "john-doe": "name:\n  given: John\n  surname: Doe\nbirth: 1948\ndeath: 2015\nportrait: john.png\n",
    }
    for pid, front in people.items():
        (data / "people" / f"{pid}.md").write_text(f"---\nid: {pid}\n{front}---\n", encoding="utf-8")
    (data / "media").mkdir(exist_ok=True)
    (data / "media" / "john.png").write_bytes(PNG)
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
