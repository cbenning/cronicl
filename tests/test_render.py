import json
from datetime import date

from famsite.model import Event, LifeEvent
from famsite.render import build_site, dumps, page_links, person_payload

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
    assert 'href="../../tree/#focus/smith-bob"' in page


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
    assert "aged 69" in html
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
    index = (tmp_path / "tree/index.html").read_text(encoding="utf-8")
    assert f'src="../viewer.js?v={js}"' in index and f'href="../style.css?v={css}"' in index
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


def test_home_and_viewer_are_separate_pages(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    viewer = (tmp_path / "tree/index.html").read_text(encoding="utf-8")
    assert 'id="tree"' in viewer and 'id="tree"' not in home
    assert "location.replace('tree.html' + location.hash)" in home
    assert 'action="people/index.html"' in home
    page = (tmp_path / "p/smith-bob/index.html").read_text(encoding="utf-8")
    assert 'href="../../tree/#focus/smith-bob"' in page and "index.html#/" not in page and "tree.html" not in page
    assert 'action="../../people/index.html"' in page


def test_home_page_content(tmp_path, make_tree):
    tree = sample(make_tree)
    tree.people["smith-bob"].birth = Event(date="1950-03-12")
    tree.site["intro"] = "Welcome to **our** family. <script>alert(1)</script>"
    build_site(
        tree, tmp_path, today=TODAY,
        recent=[{"id": "smith-bob", "date": "2026-02-02"}, {"id": "ghost", "date": "2026-01-01"}],
    )
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<h1>Test Family</h1>" in home
    assert "<strong>our</strong>" in home and "<script>alert(1)</script>" not in home
    assert "5 people" in home and "3 generations" in home and "1920–2024" in home
    assert 'href="people/index.html#s-smith"' in home
    assert 'href="p/smith-john/"' in home  # the home person card
    assert '<li data-md="03-12" hidden>' in home and "Bob Smith born" in home
    assert "2 February 2026" in home and "ghost" not in home


def test_home_page_of_an_empty_site(tmp_path, make_tree):
    build_site(make_tree([]), tmp_path, today=TODAY)
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "No people yet" in home and "Recently updated" not in home


def test_people_index_groups_by_surname(tmp_path, make_tree):
    tree = make_tree([p("a", "Ann", "Müller"), p("b", "Bo", "MULLER"), p("c", "Cy", None), p("d", "Di", "Abel")])
    build_site(tree, tmp_path, today=TODAY)
    page = (tmp_path / "people/index.html").read_text(encoding="utf-8")
    assert page.count('id="s-muller"') == 1
    assert page.index('id="s-abel"') < page.index('id="s-muller"') < page.index('id="s-none"')
    assert 'href="../p/a/"' in page and 'data-text="Ann Müller  a"' in page
    assert (tmp_path / "site.js").exists()


def test_people_index_of_an_empty_site(tmp_path, make_tree):
    build_site(make_tree([]), tmp_path, today=TODAY)
    assert "No people yet" in (tmp_path / "people/index.html").read_text(encoding="utf-8")


def test_places_page_is_written_even_when_empty(tmp_path, make_tree):
    build_site(make_tree([p("a", "Ann", "X")]), tmp_path, today=TODAY)
    assert "No places recorded yet" in (tmp_path / "places/index.html").read_text(encoding="utf-8")


def test_places_page_lists_people_under_each_place(tmp_path, make_tree):
    tree = make_tree([p("a", "Ann", "X", birth=Event(date="1900-02-03", place="Guelph"))])
    build_site(tree, tmp_path, today=TODAY)
    page = (tmp_path / "places/index.html").read_text(encoding="utf-8")
    assert 'id="pl-guelph"' in page and 'href="../p/a/"' in page and "born 3 February 1900" in page


def test_every_page_names_its_root_for_the_scripts(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    assert '<meta name="famsite-root" content="">' in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<meta name="famsite-root" content="../">' in (tmp_path / "tree/index.html").read_text(encoding="utf-8")
    assert '<meta name="famsite-root" content="../">' in (tmp_path / "people/index.html").read_text(encoding="utf-8")
    page = (tmp_path / "p/smith-bob/index.html").read_text(encoding="utf-8")
    assert '<meta name="famsite-root" content="../../">' in page
    assert 'data-kin-for="smith-bob"' in page and 'id="set-me"' in page
    assert page.index("kin.js") < page.index("site.js")


def test_relate_page_lists_everyone(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    page = (tmp_path / "relate/index.html").read_text(encoding="utf-8")
    assert page.count('<option value="smith-bob"') == 2 and 'id="relate-answer"' in page
    assert "needs JavaScript" in page  # inside <noscript>
    person = (tmp_path / "p/smith-bob/index.html").read_text(encoding="utf-8")
    assert 'href="../../relate/index.html?b=smith-bob"' in person


def page_of(tmp_path, make_tree, pid):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    return (tmp_path / f"p/{pid}/index.html").read_text(encoding="utf-8")


def test_person_page_structure(tmp_path, make_tree):
    page = page_of(tmp_path, make_tree, "smith-bob")
    assert '<p class="summary">Born 1950. Died 2020, aged 70.</p>' in page
    for gone in ('class="lifeline"', 'class="mini-tree"', 'class="facts"', 'class="side-col"'):
        assert gone not in page
    parents = page[page.index('class="fam-parents"'):page.index('class="fam-partners"')]
    assert 'href="../smith-john/"' in parents and 'href="../brown-mary/"' in parents
    assert 'href="../jones-jane/"' in page[page.index('class="fam-partners"'):page.index('class="fam-children"')]
    assert 'class="fam-siblings"' not in page  # Bob has none: no empty block


def test_person_page_pedigree_and_outline(tmp_path, make_tree):
    amy = page_of(tmp_path, make_tree, "smith-amy")
    ped = amy[amy.index('class="pedigree"'):]
    assert 'href="../smith-john/"' in ped and "<summary>Ancestors</summary>" in ped
    assert 'class="outline"' not in amy
    john = page_of(tmp_path / "j", make_tree, "smith-john")
    assert "<summary>Descendants (2)</summary>" in john and 'class="pedigree"' not in john


def test_a_bare_person_page_has_no_empty_parts(tmp_path, make_tree):
    build_site(make_tree([p("a", "Ann", None)]), tmp_path, today=TODAY)
    page = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    for absent in ('class="summary"', 'class="years"', 'class="bio"', 'class="family"', 'class="life"', "<details"):
        assert absent not in page
    assert "<h1>Ann</h1>" in page


def test_a_redacted_placeholder_page_says_nothing(tmp_path, make_tree):
    tree = make_tree([
        p("old", "Old", "X", birth=Event(date="1800")),
        p("kid", "Kid", "X", birth=Event(date="2000", place="Secretville"), parents=["old"]),
    ])
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    build_site(tree, tmp_path, today=TODAY)
    page = next(f for f in (tmp_path / "p").glob("living-*/index.html")).read_text(encoding="utf-8")
    for absent in ('class="summary"', 'class="years"', "Secretville", "2000", "<img"):
        assert absent not in page


def test_person_page_is_deterministic(tmp_path, make_tree):
    def build(target):
        build_site(sample(make_tree), target, today=TODAY)
        return (target / "p/smith-bob/index.html").read_bytes()

    assert build(tmp_path / "one") == build(tmp_path / "two")


def test_svgviews_is_gone():
    import importlib.util

    assert importlib.util.find_spec("famsite.svgviews") is None


def media_tree(make_tree, tmp_path):
    media = tmp_path / "data" / "media"
    (media / "scans").mkdir(parents=True)
    (media / "scans" / "ann #1.jpg").write_bytes(b"ANN")
    (media / "kid.jpg").write_bytes(b"KIDBYTES")
    (tmp_path / "data" / "secret.jpg").write_bytes(b"SECRET")
    tree = make_tree([
        {"id": "a", "given": "Ann", "birth": Event(date="1800"), "portrait": "scans/ann #1.jpg"},
        {"id": "b", "given": "Bea", "birth": Event(date="1801"), "portrait": "scans/ann #1.jpg"},
        {"id": "c", "given": "Cy", "birth": Event(date="1802"), "portrait": "../secret.jpg"},
        {"id": "kid", "given": "Kid", "birth": Event(date="2000"), "portrait": "kid.jpg"},
    ])
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}}
    return tree, media


def test_portraits_are_copied_and_named_in_the_payload(tmp_path, make_tree):
    tree, media = media_tree(make_tree, tmp_path)
    out = tmp_path / "out"
    build_site(tree, out, today=TODAY, media_dir=media)
    assert (out / "media/scans/ann #1.jpg").read_bytes() == b"ANN"
    payload = json.loads((out / "data/people/a.json").read_text(encoding="utf-8"))
    assert payload["image"] == {"src": "media/scans/ann%20%231.jpg", "alt": "Portrait of Ann"}
    assert json.loads((out / "data/people/c.json").read_text(encoding="utf-8"))["image"] is None
    copied = sorted(str(f.relative_to(out / "media")) for f in (out / "media").rglob("*") if f.is_file())
    assert copied == ["scans/ann #1.jpg"]
    everything = b"".join(f.read_bytes() for f in out.rglob("*") if f.is_file())
    assert b"KIDBYTES" not in everything and b"kid.jpg" not in everything and b"SECRET" not in everything
    assert 'src="../../media/scans/ann%20%231.jpg"' in (out / "p/a/index.html").read_text(encoding="utf-8")
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert {e["id"]: e["image"] for e in index if e["id"] in "abc"} == {
        "a": "media/scans/ann%20%231.jpg", "b": "media/scans/ann%20%231.jpg", "c": None}


def test_a_removed_portrait_leaves_no_stale_copy(tmp_path, make_tree):
    tree, media = media_tree(make_tree, tmp_path)
    out = tmp_path / "out"
    build_site(tree, out, today=TODAY, media_dir=media)
    for person in tree.people.values():
        person.portrait = None
    build_site(tree, out, today=TODAY, media_dir=media)
    assert not (out / "media").exists()


def test_page_prints_facts_notes_and_sources_escaped(tmp_path, make_tree):
    tree = make_tree([{
        "id": "a", "given": "Ann",
        "birth": Event(date="1920", extra={"cite": "Parish register", "note": "At home"}),
        "events": [
            LifeEvent(type="occupation", value="Carpenter <b>", note="Self-employed", cite=["Census 1911"]),
            LifeEvent(type="graduation"),
            LifeEvent(type="residence", start="1960-05", end="1975", place="Surrey", cite=["Directory"]),
        ],
    }])
    build_site(tree, tmp_path, today=TODAY)
    page = (tmp_path / "p/a/index.html").read_text(encoding="utf-8")
    assert "Carpenter &lt;b&gt;" in page and "Carpenter <b>" not in page
    assert "Source: Census 1911" in page and "Source: Parish register" in page
    assert "Self-employed" in page and "Graduation" in page and "May 1960 – 1975" in page


def test_page_links():
    site = {"edit_url": "https://example.org/fam/edit/main/people/{id}.md", "contact": "mailto:tree@example.org"}
    assert page_links(site, "smith-bob", "Bob & Co? #1") == [
        {"href": "https://example.org/fam/edit/main/people/smith-bob.md", "text": "Edit this page"},
        {"href": "mailto:tree@example.org?subject=Correction%3A%20Bob%20%26%20Co%3F%20%231%20%28smith-bob%29",
         "text": "Suggest a correction"}]
    assert page_links({"contact": "https://example.org/contact"}, "a", "A") == [
        {"href": "https://example.org/contact", "text": "Suggest a correction"}]
    assert page_links({"edit_url": "https://example.org/no-placeholder", "contact": "javascript:alert(1)"}, "a", "A") == []
    assert page_links({}, "a", "A") == []


def test_links_are_printed_for_real_people_only(tmp_path, make_tree):
    tree = make_tree([
        p("old", "Old", "X", birth=Event(date="1800")),
        p("kid", "Kid", "X", birth=Event(date="2000"), parents=["old"]),
    ])
    tree.site = {"privacy": {"living": "placeholder", "id_salt": "s"}, "contact": "mailto:tree@example.org"}
    build_site(tree, tmp_path, today=TODAY)
    pages = {f.parent.name: f.read_text(encoding="utf-8") for f in (tmp_path / "p").glob("*/index.html")}
    assert "Suggest a correction" in pages["old"]
    assert all("Suggest a correction" not in html for pid, html in pages.items() if pid != "old")


def test_each_view_has_its_own_address_and_one_nav(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    tree = (tmp_path / "tree/index.html").read_text(encoding="utf-8")
    timeline = (tmp_path / "timeline/index.html").read_text(encoding="utf-8")
    assert '<body data-page="tree">' in tree and '<body data-page="timeline">' in timeline
    for page, root in ((tmp_path / "index.html", ""), (tmp_path / "people/index.html", "../"), (tmp_path / "tree/index.html", "../")):
        text = page.read_text(encoding="utf-8")
        assert f'<a href="{root}tree/"' in text and f'<a href="{root}timeline/"' in text
        assert f'<a href="{root}places/index.html"' in text
        assert root == "" or "tree.html" not in text  # the home page's old-link forwarder is the only mention
    assert tree.count('aria-label="Site"') == 1 and 'id="tabs"' not in tree  # one nav; no second tab bar
    assert '<a href="../tree/" aria-current="page">Tree</a>' in tree
    assert '<a href="../timeline/" aria-current="page">Timeline</a>' in timeline


def test_the_old_viewer_address_forwards(tmp_path, make_tree):
    build_site(sample(make_tree), tmp_path, today=TODAY)
    old = (tmp_path / "tree.html").read_text(encoding="utf-8")
    assert "location.replace(" in old and "tree/" in old and "timeline/" in old and 'id="tree"' not in old


def test_places_page_is_grouped_by_country(tmp_path, make_tree):
    tree = make_tree([
        p("a", "Ann", "X", birth=Event(date="1900", place="Hamburg, Germany")),
        p("b", "Bo", "X", birth=Event(date="1901", place="Duncan, British Columbia, Canada")),
        p("c", "Cy", "X", birth=Event(date="1902", place="Barrie, Ontario, Canada")),
    ])
    tree.site = {"place_groups": {"British Columbia": "Canada"}}
    build_site(tree, tmp_path, today=TODAY)
    page = (tmp_path / "places/index.html").read_text(encoding="utf-8")
    assert page.index('id="c-canada"') < page.index('id="pl-duncan-british-columbia-canada"') < page.index('id="c-germany"')
    assert 'href="#c-germany"' in page


GALLERY = {"type": "fussel", "url": "https://x.example/photos"}


def _gallery_site(make_tree, people, gallery=GALLERY, **site):
    tree = make_tree(people)
    tree.site = {"gallery": gallery, **site}
    return tree


def _page(tmp_path, pid="a"):
    return (tmp_path / f"p/{pid}/index.html").read_text(encoding="utf-8")


def test_no_gallery_changes_nothing(tmp_path, make_tree):
    build_site(make_tree([p("a", "Ann", "X")]), tmp_path, today=TODAY)
    assert not (tmp_path / "gallery.js").exists()
    for rel in ("p/a/index.html", "index.html", "people/index.html"):
        assert "gallery" not in (tmp_path / rel).read_text(encoding="utf-8").lower()


def test_invalid_gallery_changes_nothing(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X")], gallery={"type": "fussel"})
    build_site(tree, tmp_path, today=TODAY)
    assert not (tmp_path / "gallery.js").exists()
    assert "gallery" not in _page(tmp_path).lower()


def test_gallery_block_and_attributes(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X", body="Bio text.\n", parents=["b"]), p("b", "Bob", "X")])
    build_site(tree, tmp_path, today=TODAY)
    page = _page(tmp_path)
    assert (tmp_path / "gallery.js").exists()
    assert 'id="gallery"' in page and "hidden" in page.split('id="gallery"')[1].split(">")[0]
    assert 'data-gallery-url="https://x.example/photos/"' in page
    assert 'data-gallery-type="fussel"' in page
    assert 'data-gallery-key="ann-x"' in page
    assert 'data-gallery-explicit="0"' in page
    assert 'data-gallery-name="Ann X"' in page
    assert "<h2>Photos</h2>" in page
    assert 'src="../../gallery.js?v=' in page
    assert page.index("Bio text.") < page.index('id="gallery"') < page.index('<section class="family">')


def test_gallery_id_overrides_the_slug(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X", gallery_id="the-ann")])
    build_site(tree, tmp_path, today=TODAY)
    page = _page(tmp_path)
    assert 'data-gallery-key="the-ann"' in page and 'data-gallery-explicit="1"' in page


def test_gallery_label_is_escaped(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X")], gallery={**GALLERY, "label": "<b>x</b>"})
    build_site(tree, tmp_path, today=TODAY)
    page = _page(tmp_path)
    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page


def test_header_link_on_every_page(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X")])
    build_site(tree, tmp_path, today=TODAY)
    link = '<a class="site-gallery" href="https://x.example/photos/" target="_blank" rel="noopener">Photos</a>'
    for rel in ("index.html", "people/index.html", "places/index.html", "relate/index.html", "tree/index.html",
                "timeline/index.html", "p/a/index.html"):
        assert link in (tmp_path / rel).read_text(encoding="utf-8"), rel


def test_redacted_living_person_has_no_gallery_block(tmp_path, make_tree):
    people = [
        p("old", "Old", "Timer", birth=Event(date="1900"), death=Event(date="1950")),
        p("kid", "Kid", "Now", birth=Event(date="2020")),
    ]
    tree = _gallery_site(make_tree, people, privacy={"living": "placeholder"})
    build_site(tree, tmp_path, today=TODAY)
    assert 'id="gallery"' in _page(tmp_path, "old")
    for page_dir in (tmp_path / "p").iterdir():
        if page_dir.name != "old":
            assert 'id="gallery"' not in (page_dir / "index.html").read_text(encoding="utf-8")


def test_nameless_person_has_no_gallery_block(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [{"id": "a"}])
    build_site(tree, tmp_path, today=TODAY)
    assert 'id="gallery"' not in _page(tmp_path)


def test_long_name_key_is_not_truncated(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "z" * 70)])
    build_site(tree, tmp_path, today=TODAY)
    assert 'data-gallery-key="ann-' + "z" * 70 + '"' in _page(tmp_path)


def test_gallery_styles_exist(tmp_path, make_tree):
    build_site(make_tree([p("a", "Ann", "X")]), tmp_path, today=TODAY)
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    assert ".gallery-thumbs" in css and ".site-gallery" in css
    printed = css.split("@media print", 1)[1].split("}", 1)[0]
    assert ".gallery" in printed


def test_names_that_do_not_fold_cleanly_get_no_derived_key(tmp_path, make_tree):
    tree = _gallery_site(
        make_tree,
        [p("a", "\u0418\u0432\u0430\u043d", "Smith"), p("b", "Zo\u00eb", "M\u00fcller"), p("c", "\u0418\u0432\u0430\u043d", "Smith", gallery_id="ivan-smith")],
    )
    build_site(tree, tmp_path, today=TODAY)
    assert 'id="gallery"' not in _page(tmp_path, "a")
    assert 'data-gallery-key="zoe-muller"' in _page(tmp_path, "b")
    assert 'data-gallery-key="ivan-smith"' in _page(tmp_path, "c") and 'data-gallery-explicit="1"' in _page(tmp_path, "c")


def test_portrait_fallback_attribute(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X")])
    build_site(tree, tmp_path, today=TODAY)
    assert 'data-gallery-portrait="1"' in _page(tmp_path)


def test_portraits_false_turns_the_fallback_off(tmp_path, make_tree):
    tree = _gallery_site(make_tree, [p("a", "Ann", "X")], gallery={**GALLERY, "portraits": False})
    build_site(tree, tmp_path, today=TODAY)
    assert 'data-gallery-portrait="0"' in _page(tmp_path)


def test_a_person_with_their_own_portrait_never_gets_the_fallback(tmp_path, make_tree):
    media = tmp_path / "media"
    media.mkdir()
    (media / "ann.jpg").write_bytes(b"ANN")
    tree = _gallery_site(make_tree, [p("a", "Ann", "X", portrait="ann.jpg"), p("b", "Bob", "X")])
    out = tmp_path / "out"
    build_site(tree, out, today=TODAY, media_dir=media)
    assert 'data-gallery-portrait="0"' in _page(out, "a")
    assert 'data-gallery-portrait="1"' in _page(out, "b")


def test_gallery_display_styles_exist(tmp_path, make_tree):
    build_site(make_tree([p("a", "Ann", "X")]), tmp_path, today=TODAY)
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    for selector in (".gallery-lightbox", ".gallery-thumbs li.featured", ".gallery-count"):
        assert selector in css, selector
    reduced = css.split("prefers-reduced-motion", 1)[1].split("}", 2)[0:2]
    assert ".gallery-lightbox" in "".join(reduced)
    printed = css.split("@media print", 1)[1].split("}", 1)[0]
    assert ".gallery-lightbox" in printed


def test_settings_in_odd_shapes_never_raise(tmp_path, make_tree):
    people = [p("old", "Old", "Timer", birth=Event(date="1900"), death=Event(date="1950")), p("kid", "Kid", "Now", birth=Event(date="2020"))]
    tree = make_tree(people)
    tree.site = {"privacy": {"living": "Placeholder", "cutoff_years": "25", "id_salt": "s"}}
    build_site(tree, tmp_path / "a", today=TODAY)
    assert "Kid" not in (tmp_path / "a/index.json").read_text(encoding="utf-8")
    tree.site = {"title": ["x"], "intro": {"a": 1}}
    build_site(tree, tmp_path / "b", today=TODAY)
    page = (tmp_path / "b/index.html").read_text(encoding="utf-8")
    assert "Family Tree" in page and "['x']" not in page and "{'a': 1}" not in page
    tree.site = {"place_groups": "Ontario"}
    build_site(tree, tmp_path / "c", today=TODAY)
