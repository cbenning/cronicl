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
    assert 'href="../../index.html#/tree/smith-bob"' in page  # canonical route; bare #/<id> still works


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


def test_ended_partnership_details_of_a_living_person_reach_no_output_file(tmp_path, make_tree):
    from famsite.model import Partnership

    tree = make_tree(
        [
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), death=Event(date="2020"),
              partnerships=[
                  Partnership(
                      "zzcurtis-jane", type="marriage", start="1971-02-03", end="1983-04-05",
                      end_reason="divorce", place="Qqplace", note="Qqnote",
                  )
              ]),
            p("zzcurtis-jane", "Jane", "Zzcurtis", birth=Event(date="1952")),
        ]
    )
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    for rel, data in read_all(tmp_path).items():
        if rel in ("viewer.js", "style.css"):
            continue  # static assets contain the words "divorce" and "divorced" themselves
        text = data.decode("utf-8", errors="ignore")
        for secret in ("Qqplace", "Qqnote", "1971", "1983", "divorce", "divorced"):
            assert secret not in text, (rel, secret)


def test_no_privacy_setting_means_no_redaction(tmp_path, make_tree):
    tree = make_tree([p("a", "Al", "Living", birth=Event(date="2000"))])
    tree.site = {}
    build_site(tree, tmp_path, today=TODAY)
    payload = json.loads((tmp_path / "data/people/a.json").read_text(encoding="utf-8"))
    assert payload["name"] == "Al Living"


def test_spouse_payload_carries_partnership_text(make_tree):
    from famsite.model import Partnership

    tree = make_tree(
        [
            {"id": "a", "given": "A", "partnerships": [
                Partnership("b", type="marriage", start="1975", end="1990", end_reason="divorce", place="Surrey, BC")
            ]},
            {"id": "b", "given": "B"},
        ]
    )
    spouse = person_payload(tree, "a")["spouses"][0]
    assert spouse["id"] == "b" and "marriage" not in spouse
    assert spouse["partnerships"] == [
        {
            "type": "marriage", "start": "1975", "end": "1990", "end_reason": "divorce", "place": "Surrey, BC",
            "note": None, "text": "Married 1975 – divorced 1990 (Surrey, BC)",
        }
    ]


def test_partnership_text_wording():
    from famsite.render import partnership_text

    assert partnership_text("marriage", "1975", None, None, None) == "Married 1975"
    assert partnership_text("marriage", "1975", "1990", None, None) == "Married 1975 – ended 1990"
    assert partnership_text("marriage", None, "unknown", "divorce", None) == "Married – divorced"
    assert partnership_text("partnership", "1990", "2001", None, None) == "Partners 1990 – ended 2001"
    assert partnership_text("engagement", "1974", None, None, None) == "Engaged 1974"
    assert partnership_text("civil-union", "2005", "2010", "separation", None) == "Civil union 2005 – separated 2010"
    assert partnership_text("marriage", "1950", "1951", "annulment", None) == "Married 1950 – annulled 1951"
    assert partnership_text("unknown", None, None, None, None) == ""
    assert partnership_text(None, None, None, None, "Reno") == "Partners (Reno)"


def test_person_page_has_hero_facts_events_and_family(tmp_path, make_tree):
    tree = make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920-05-01", place="Halifax, NS"),
              death=Event(date="1990-02-03", place="Toronto, ON"), body="Teacher & friend."),
            p("brown-mary", "Mary", "Brown", birth=Event(date="1925")),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), parents=["smith-john", "brown-mary"]),
            p("smith-sue", "Sue", "Smith", birth=Event(date="1952"), parents=["smith-john"]),
        ]
    )
    tree.site = {"title": "Fam"}
    build_site(tree, tmp_path, today=TODAY)
    html = (tmp_path / "p/smith-john/index.html").read_text(encoding="utf-8")
    assert "<h1>John Smith</h1>" in html
    assert 'class="avatar avatar-lg"' in html and ">JS<" in html
    assert "Halifax, NS" in html and "Toronto, ON" in html
    assert "Age" in html and "69" in html
    assert "Bob Smith born" in html
    assert 'data-slot="gallery"' not in html  # nothing configured yet
    assert "../smith-bob/" in html


def test_person_with_nothing_known_has_no_dangling_labels(tmp_path, make_tree):
    tree = make_tree([{"id": "unknown-i1"}])
    build_site(tree, tmp_path, today=TODAY)
    html = (tmp_path / "p/unknown-i1/index.html").read_text(encoding="utf-8")
    assert ">?<" in html
    for label in ("Born", "Died", "Age", "Life events", "Parents", "Siblings", "Partners", "Children"):
        assert label not in html, label


def test_person_page_escapes_names_and_places(tmp_path, make_tree):
    tree = make_tree([p("a", "Al", "O'Neil <b>", birth=Event(date="1900", place='"Quote" & <i>Town</i>'))])
    build_site(tree, tmp_path, today=TODAY)
    html = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    assert "<b>" not in html and "<i>" not in html
    assert "&lt;b&gt;" in html and "&amp;" in html


def test_living_relatives_stay_hidden_on_the_page_end_to_end(tmp_path, make_tree):
    tree = make_tree(
        [
            p("old", "Olga", "Zzold", birth=Event(date="1900"), death=Event(date="1970")),
            p("me", "Moe", "Qqme", birth=Event(date="1990"), parents=["old"]),
            p("sib", "Sid", "Wwsib", birth=Event(date="1992"), parents=["old"]),
        ]
    )
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    for rel, data in read_all(tmp_path).items():
        text = data.decode("utf-8", errors="ignore")
        assert "Qqme" not in text and "Wwsib" not in text, rel
    assert (tmp_path / "p/old/index.html").exists()


def test_person_page_embeds_lifeline_and_tree_and_is_deterministic(tmp_path, make_tree):
    def build(target):
        tree = make_tree(
            [
                p("smith-john", "John", "Smith", birth=Event(date="1920"), death=Event(date="1990")),
                p("brown-mary", "Mary", "Brown", birth=Event(date="1925")),
                p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), parents=["smith-john", "brown-mary"]),
            ]
        )
        build_site(tree, target, today=TODAY)
        return (target / "p/smith-bob/index.html").read_bytes()

    first = build(tmp_path / "one")
    assert b'class="mini-tree"' in first and b'class="lifeline"' in first
    assert b'href="../smith-john/"' in first
    assert first == build(tmp_path / "two")


def test_timeline_json_does_not_repeat_every_persons_events(tmp_path, make_tree):
    tree = make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920"), death=Event(date="1990")),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950"), parents=["smith-john"]),
        ]
    )
    build_site(tree, tmp_path, today=TODAY)
    timeline = json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))
    assert all("events" not in person for person in timeline["people"].values())
    assert timeline["people"]["smith-bob"]["parents"] == ["smith-john"]  # relationships stay
    assert all("text" in e for e in timeline["events"])  # the family view's wording stays
    payload = json.loads((tmp_path / "data/people/smith-bob.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in payload["events"]] == ["birth:smith-bob", "death:smith-john"]


def test_assets_are_versioned_by_content_so_a_rebuild_is_never_served_stale(tmp_path, make_tree):
    import hashlib
    from pathlib import Path

    import famsite

    tree = make_tree([p("a", "Al", "X")])
    build_site(tree, tmp_path, today=TODAY)
    root = Path(famsite.__file__).parent / "viewer"
    js = hashlib.sha256((root / "viewer.js").read_bytes()).hexdigest()[:12]
    css = hashlib.sha256((root / "style.css").read_bytes()).hexdigest()[:12]
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert f'src="viewer.js?v={js}"' in index and f'href="style.css?v={css}"' in index
    page = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    assert f'href="../../style.css?v={css}"' in page


def test_person_page_prints_dates_in_words(tmp_path, make_tree):
    tree = make_tree([p("a", "Ann", "X", birth=Event(date="1941-03-12"), death=Event(date="2021-06-04"))])
    build_site(tree, tmp_path, today=TODAY)
    page = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    assert "12 March 1941" in page and "1941-03-12" not in page


def test_pages_name_the_home_person(tmp_path, make_tree):
    tree = sample(make_tree)
    build_site(tree, tmp_path, today=TODAY)
    assert '<meta name="famsite-home" content="smith-john">' in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<meta name="famsite-home" content="smith-john">' in (tmp_path / "p/smith-bob/index.html").read_text(encoding="utf-8")


def test_an_empty_site_has_no_home_person(tmp_path, make_tree):
    build_site(make_tree([]), tmp_path, today=TODAY)
    assert '<meta name="famsite-home" content="">' in (tmp_path / "index.html").read_text(encoding="utf-8")
