"""The optional map: site.yml `places:` and `map:`, the page, map.json, and what never reaches them."""
import json

import pytest

from cronicl.cli import main
from cronicl.site.mapdata import map_settings, place_coords

FAMILY = """\
ada:
  name: {given: Ada, surname: Lovelace}
  birth: {date: 1815, place: "London, England"}
  death: {date: 1852, place: "Ockham, Surrey"}
bob:
  name: {given: Bob, surname: Smith}
  birth: {date: 1900, place: "london, england"}
"""
SITE = """\
title: T
schema_version: 3
places:
  "London, England": [51.5072, -0.1276]
map:
  type: osm
"""


def make(tmp_path, write_family, site=SITE, family=FAMILY):
    root = tmp_path / "data"
    write_family(root, family)
    (root / "site.yml").write_text(site, encoding="utf-8")
    return root


def build(tmp_path, write_family, **kw):
    root = make(tmp_path, write_family, **kw)
    out = tmp_path / "out"
    assert main(["build", "--dir", str(root), "--out", str(out)]) == 0
    return out


def codes(root, capsys):
    capsys.readouterr()
    main(["check", "--dir", str(root), "--format", "json"])
    return sorted({i["code"] for i in json.loads(capsys.readouterr().out)})


def test_no_map_block_means_no_map_files_no_link_and_no_script(tmp_path, write_family):
    out = build(tmp_path, write_family, site="title: T\nschema_version: 3\nplaces:\n  London, England: [51.5, -0.1]\n")
    assert not (out / "map").exists() and not (out / "map.json").exists() and not (out / "map.js").exists()
    for page in out.rglob("*.html"):
        assert "map/" not in page.read_text(encoding="utf-8") and "tile." not in page.read_text(encoding="utf-8"), page


def test_a_valid_block_builds_the_page_the_data_and_the_links(tmp_path, write_family):
    out = build(tmp_path, write_family)
    markers = json.loads((out / "map.json").read_text(encoding="utf-8"))
    assert [m["name"] for m in markers] == ["London, England"]
    assert (markers[0]["lat"], markers[0]["lon"]) == (51.5072, -0.1276)
    assert sorted(e["id"] for e in markers[0]["entries"]) == ["ada", "bob"]  # case and spacing do not split a place
    page = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert 'data-tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png"' in page and "© OpenStreetMap contributors" in page
    assert (out / "map.js").exists()
    assert 'href="map/"' in (out / "index.html").read_text(encoding="utf-8")
    places = (out / "places" / "index.html").read_text(encoding="utf-8")
    assert f'href="../map/#{markers[0]["slug"]}"' in places and places.count("on the map") == 1


def test_a_living_persons_place_is_not_a_marker(tmp_path, write_family):
    family = FAMILY + "kid:\n  name: {given: Secretname, surname: Livingperson}\n  birth: {date: 2015, place: Hiddenville}\n"
    site = SITE.replace("map:", '  "Hiddenville": [10, 10]\nmap:').replace("privacy", "privacy") + "privacy:\n  living: placeholder\n  id_salt: s\n"
    out = build(tmp_path, write_family, site=site, family=family)
    assert "Hiddenville" not in (out / "map.json").read_text(encoding="utf-8")
    for f in out.rglob("*"):
        if f.is_file():
            assert "Secretname" not in f.read_text(encoding="utf-8", errors="ignore"), f


def test_hostile_text_is_escaped_in_the_page_and_stays_data_in_the_json(tmp_path, write_family):
    family = 'x:\n  name: {given: X}\n  birth: {date: 1900, place: "<script>alert(1)</script>, Y"}\n'
    site = (
        'title: T\nschema_version: 3\nplaces:\n  "<script>alert(1)</script>, Y": [1, 2]\n'
        'map:\n  type: osm\n  attribution: "<img src=x onerror=alert(1)>"\n  label: "<b>Map</b>"\n'
    )
    out = build(tmp_path, write_family, site=site, family=family)
    page = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert "<script>alert" not in page and "<img src=x" not in page and "<b>Map" not in page
    assert json.loads((out / "map.json").read_text(encoding="utf-8"))[0]["name"] == "<script>alert(1)</script>, Y"
    assert "<script>alert" not in (out / "places" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "tiles, valid",
    [
        ("https://tiles.example.org/{z}/{x}/{y}.png", True),
        ("http://127.0.0.1:8000/{z}/{x}/{y}.png", True),
        ("https://t.example.org/{z}/{x}/{y}.png?key=abc", True),
        ("ftp://t.example.org/{z}/{x}/{y}.png", False),
        ("javascript:alert(1)//{z}{x}{y}", False),
        ("https://t.example.org/{z}/{x}/{y}.png\"onload=1", False),
        ("https://t.example.org/{z}/{x}.png", False),
        ("https://t.example.org/{z}/{x}/{y}/{s}.png", False),
        ("https://t.example.org/{z}/{x}/{y}/{{z}}.png", False),
        ("https://user:pw@t.example.org/{z}/{x}/{y}.png", False),
        ("//t.example.org/{z}/{x}/{y}.png", False),
    ],
)
def test_tile_templates_are_checked(tiles, valid):
    assert (map_settings({"map": {"type": "osm", "tiles": tiles}}) is not None) is valid


@pytest.mark.parametrize(
    "bad",
    [["91", "0"], ["0", "181"], ["nan", "0"], ["inf", "0"], ["x", "y"], ["1"], "51.5, -0.1", ["1", "2", "3"], {"lat": "1"}],
)
def test_bad_coordinates_are_skipped(bad):
    assert place_coords({"places": {"Here": bad, "There": ["1.5", "-2"]}}) == {"there": (1.5, -2.0)}


def test_validation_codes(tmp_path, write_family, capsys):
    def run(site):
        return codes(make(tmp_path, write_family, site=site), capsys)

    head = "title: T\nschema_version: 3\n"
    assert "E-MAP-TYPE" in run(head + "map: yes\n")
    assert "E-MAP-TYPE" in run(head + "map:\n  type: google\n")
    assert "E-MAP-TILES" in run(head + "map:\n  type: osm\n  tiles: https://x.example/{z}/{x}.png\n")
    assert "W-MAP-KEY" in run(head + "places:\n  London, England: [1, 2]\nmap:\n  type: osm\n  zoom: 3\n")
    assert "W-MAP-NO-COORDS" in run(head + "map:\n  type: osm\n")
    assert "W-PLACE-COORDS" in run(head + "places:\n  London, England: [95, 2]\n")
    assert "W-PLACE-UNKNOWN" in run(head + "places:\n  Atlantis: [1, 2]\n")
    assert "W-SITE-VALUE" in run(head + "places: nope\n")
    assert run(SITE) == []  # a good setup is silent
    assert run(head + "places:\n  London, England: [51.5, -0.1]\n") == []  # coordinates alone are fine (export uses them)


def test_the_export_uses_the_coordinates(tmp_path, write_family, capsys):
    root = make(tmp_path, write_family)
    capsys.readouterr()
    assert main(["export-gedcom", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "2 PLAC London, England\n3 MAP\n4 LATI N51.5072\n4 LONG W0.1276" in out
    assert "ockham" not in out.lower().replace("2 plac ockham, surrey", "")  # a place without coordinates has no MAP
