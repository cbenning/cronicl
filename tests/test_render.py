import json
from datetime import date

from famsite.model import Event
from famsite.render import build_site, dumps, person_payload

TODAY = date(2026, 10, 10)


def p(pid, given, surname, **kw):
    return {"id": pid, "given": given, "surname": surname, **kw}


def sample(make_tree):
    tree = make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920"), death=Event(date="1990"),
              body="Worked as a <script>alert(1)</script> teacher.\n\nSecond **para**."),
            p("brown-mary", "Mary", "Brown", birth=Event(date="1925"), death=Event(date="2001")),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), death=Event(date="2020"),
              parents=["smith-john", "brown-mary"]),
            p("smith-amy", "Amy", "O'Smith <b>", birth=Event(date="1980"), death=Event(date="2024"),
              parents=["smith-bob", "jones-jane"]),
            p("jones-jane", "Jane", "Jones", birth=Event(date="1952"), death=Event(date="2023")),
        ]
    )
    tree.site = {"title": "Test Family", "privacy": {"living": "placeholder", "id_salt": "s"}}
    return tree


def read_all(root):
    return {str(f.relative_to(root)): f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()}


def test_person_payload_has_relatives(make_tree):
    tree = sample(make_tree)
    payload = person_payload(tree, "smith-bob")
    assert payload["name"] == "Bob Smith"
    assert payload["years"] == "1950–2020"
    assert [r["id"] for r in payload["parents"]] == ["smith-john", "brown-mary"]
    assert [r["id"] for r in payload["spouses"]] == ["jones-jane"]
    assert [r["id"] for r in payload["children"]] == ["smith-amy"]


def test_single_parent_payload_has_children_but_no_spouse(make_tree):
    tree = make_tree([p("a", "A", "X"), p("c", "C", "X", parents=["a"])])
    payload = person_payload(tree, "a")
    assert payload["spouses"] == []
    assert [r["id"] for r in payload["children"]] == ["c"]


def test_build_writes_expected_files(tmp_path, make_tree):
    summary = build_site(sample(make_tree), tmp_path, today=TODAY)
    for rel in ["index.html", "layout.json", "index.json", "data/people/smith-bob.json", "p/smith-bob/index.html"]:
        assert (tmp_path / rel).exists(), rel
    assert summary.people == 5
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 5
    assert index == sorted(index, key=lambda e: (e["name"].lower(), e["id"]))
    layout = json.loads((tmp_path / "layout.json").read_text(encoding="utf-8"))
    assert layout["version"] == 1 and len(layout["nodes"]) == 5


def test_markdown_is_rendered_and_raw_html_is_escaped(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    payload = json.loads((tmp_path / "data/people/smith-john.json").read_text(encoding="utf-8"))
    assert "<strong>para</strong>" in payload["bodyHtml"]
    assert "<script>" not in payload["bodyHtml"]
    assert "&lt;script&gt;" in payload["bodyHtml"]


def test_templates_escape_names(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    page = (tmp_path / "p/smith-amy/index.html").read_text(encoding="utf-8")
    assert "O&#39;Smith &lt;b&gt;" in page
    assert "<b>" not in page


def test_static_person_page_links_relatives_and_back(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    page = (tmp_path / "p/smith-bob/index.html").read_text(encoding="utf-8")
    assert 'href="../smith-john/"' in page
    assert 'href="../../index.html#/smith-bob"' in page


def test_build_is_deterministic(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path / "a", today=TODAY)
    build_site(sample(make_tree), tmp_path / "b", today=TODAY)
    assert read_all(tmp_path / "a") == read_all(tmp_path / "b")


def test_dumps_is_stable_and_utf8():
    assert dumps({"b": 1, "a": "é"}) == '{\n  "a": "é",\n  "b": 1\n}\n'


def test_living_people_never_appear_in_any_output_file(tmp_path, make_tree):
    # Living: Jane (born 1952, no death) and Tom (born 2012, no death).
    tree = make_tree(
        [
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), death=Event(date="2020")),
            p("zzcurtis-jane", "Jane", "Zzcurtis", birth=Event(date="1952")),
            p("smith-tom", "Tom", "Qqwidget", birth=Event(date="2012"),
              parents=["smith-bob", "zzcurtis-jane"], body="Tom bio Qqwidget"),
        ]
    )
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    for rel, data in read_all(tmp_path).items():
        text = data.decode("utf-8", errors="ignore")
        assert "Zzcurtis" not in text and "zzcurtis" not in text, rel
        assert "Qqwidget" not in text and "qqwidget" not in text, rel
        assert "Jane" not in text and "Tom bio" not in text, rel
    assert (tmp_path / "data/people/smith-bob.json").exists()


def test_no_privacy_setting_means_no_redaction(tmp_path, make_tree):
    tree = make_tree([p("a", "Al", "Living", birth=Event(date="2000"))])
    tree.site = {}
    build_site(tree, tmp_path, today=TODAY)
    payload = json.loads((tmp_path / "data/people/a.json").read_text(encoding="utf-8"))
    assert payload["name"] == "Al Living"
