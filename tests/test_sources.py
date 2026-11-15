"""Citations: numbered footnotes on a person page and a site-wide Sources page."""
import re
from datetime import date

from cronicl.cli import main
from cronicl.site.sources import annotate, number_cites
from cronicl.site.render import build_site

TODAY = date(2026, 10, 10)

FAMILY = """\
ada:
  name: {given: Ada, surname: Lovelace}
  birth: {date: 1815-12-10, place: London, cite: Parish register}
  death: {date: 1852-11-27, cite: [Parish register, "Newspaper <b>notice</b>"]}
  events:
    - {type: occupation, value: Mathematician, cite: Letters}
    - {type: residence, date: 1840, place: Surrey, cite: Letters}
bob:
  name: {given: Bob, surname: Smith}
  birth: {date: 1900, cite: Census 1911}
  death: 1950
"""


def build(tmp_path, write_family, family=FAMILY, site="title: T\nschema_version: 3\n"):
    root = tmp_path / "data"
    write_family(root, family)
    (root / "site.yml").write_text(site, encoding="utf-8")
    out = tmp_path / "out"
    assert main(["build", "--dir", str(root), "--out", str(out)]) == 0
    return out


def test_numbering_follows_first_use_and_repeats_share_a_number():
    numbers, sources = number_cites([["b"], ["a", "b"], [], ["c", "a"]])
    assert numbers == {"b": 1, "a": 2, "c": 3}
    assert [s["text"] for s in sources] == ["b", "a", "c"]


def test_annotate_marks_only_the_first_use():
    payload = {"facts": [{"cite": ["x"]}], "events": [{"cite": ["x", "y"]}, {"cite": ["y"]}]}
    view, sources = annotate(payload)
    flat = [c for part in (view["facts"], view["events"]) for item in part for c in item["cite"]]
    assert [(c["n"], c["first"]) for c in flat] == [(1, True), (1, False), (2, True), (2, False)]
    assert payload["facts"][0]["cite"] == ["x"]  # the data payload is untouched


def test_person_page_has_superscripts_a_sources_list_and_back_links(tmp_path, write_family):
    page = (build(tmp_path, write_family) / "p" / "ada" / "index.html").read_text(encoding="utf-8")
    assert "Source:" not in page
    assert re.search(r'<sup class="cite-ref"><a href="#src-1" id="cite-1">1</a></sup>', page)
    section = page[page.index('class="sources"'):]
    assert section.count("<li") == 3  # Parish register, Newspaper, Letters -- once each
    assert 'id="src-1"' in section and 'href="#cite-1"' in section
    assert "Letters" in section and "&lt;b&gt;notice&lt;/b&gt;" in section and "<b>notice" not in page


def test_the_sources_page_lists_each_text_once_with_its_people(tmp_path, write_family):
    out = build(tmp_path, write_family)
    page = (out / "sources" / "index.html").read_text(encoding="utf-8")
    for text in ("Parish register", "Letters", "Census 1911"):
        assert page.count(text) == 1
    assert 'href="../p/ada/"' in page and 'href="../p/bob/"' in page
    assert 'href="sources/index.html"' in (out / "index.html").read_text(encoding="utf-8")


def test_no_citations_means_no_page_and_no_link(tmp_path, write_family):
    out = build(tmp_path, write_family, "a:\n  name: {given: A}\n  birth: 1900\n")
    assert not (out / "sources").exists()
    assert "sources/index.html" not in (out / "index.html").read_text(encoding="utf-8")


def test_a_living_persons_citations_are_nowhere(tmp_path, write_family):
    family = FAMILY + "kid:\n  name: {given: Secretname, surname: Livingperson}\n  birth: {date: 2015, cite: Secretsource}\n  events:\n    - {type: residence, place: Hiddenplace, cite: Secretsource}\n"
    out = build(tmp_path, write_family, family, "title: T\nschema_version: 3\nprivacy:\n  living: placeholder\n  id_salt: s\n")
    for f in out.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            assert "Secretsource" not in text and "Secretname" not in text, f


def test_output_is_deterministic(tmp_path, write_family):
    a = build(tmp_path / "1", write_family)
    b = build(tmp_path / "2", write_family)
    assert (a / "sources" / "index.html").read_bytes() == (b / "sources" / "index.html").read_bytes()


def test_the_same_source_twice_on_one_fact_is_one_footnote(tmp_path, write_family):
    out = build(tmp_path, write_family, family='a:\n  name: {given: A}\n  birth: {date: 1900, cite: ["x", "x "]}\n  death: 1950\n')
    page = (out / "p" / "a" / "index.html").read_text(encoding="utf-8")
    assert page.count('class="cite-ref"') == 1
