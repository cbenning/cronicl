"""Import and export are mirrors: what the importer maps survives export -> import unchanged."""
from datetime import date

from cronicl.cli import main
from cronicl.core.gedcom import import_nodes, parse_nodes, write_import_family
from cronicl.core.gedcom_export import export_gedcom
from cronicl.core.store import load_tree

TODAY = date(2026, 11, 15)

# Only things GEDCOM 5.5.1 has a slot for and the importer maps (see the spec's "symmetry contract").
FAMILY = """\
byron-george:
  name: {given: George, surname: Byron}
  sex: male
  birth: {date: 1788-01-22, place: "London, England", cite: Baptism register}
  death: {date: 1824-04-19, place: "Missolonghi, Greece"}
milbanke-annabella:
  name: {given: Annabella, surname: Milbanke, also: [Lady Byron]}
  sex: female
  birth: 1792-05-17
  death: unknown
byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02, place: "Seaham, England", note: Winter wedding, cite: Marriage bond}
lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace, prefix: Lady, suffix: Jr, nickname: Ada}
  sex: female
  birth: {date: 1815-12-10, note: Born at Piccadilly Terrace.}
  death: {date: 1852-11-27, cite: [Parish register, Newspaper]}
  parents: [byron-george, milbanke-annabella]
  events:
    - {type: occupation, value: Mathematician, cite: [Letters, Babbage notes]}
    - {type: residence, date: FROM 1835 TO 1852, place: "Ockham Park, Surrey", note: Summers}
    - {type: burial, date: BET 1852-11-30 AND 1852-12-03, place: Hucknall}
  bio: |
    Mathematician and writer. Mail: ada@example.org

    She is often described as the first programmer.
king-william:
  name: {given: William, surname: King}
  sex: male
  birth: ABT 1805
king-william + lovelace-ada:
  events:
    - {type: marriage, date: 1835-07-08}
    - {type: divorce, date: 1850}
    - {type: engagement, date: 1851-01}
unknown-lone:
  name: {given: Lone}
  parents: [king-william]
"""


def shape(tree):
    """The records as names and facts, independent of ids and file order."""
    names = {pid: p.display_name for pid, p in tree.people.items()}
    people = {}
    for pid, p in tree.people.items():
        people[names[pid]] = {
            "name": (p.given, p.surname, p.prefix, p.suffix, p.nickname, tuple(p.also)),
            "sex": p.sex,
            "birth": _vital(p.birth), "death": _vital(p.death),
            "parents": tuple(sorted(names[x] for x in p.parents)),
            "events": [(e.type, e.date, e.start, e.end, e.place, e.value, e.note, tuple(e.cite)) for e in p.events],
            "bio": p.body,
            "couples": sorted(
                (names[pid], names[q.with_id], q.type, q.start, q.end, q.end_reason, q.place, q.note, tuple(q.cite))
                for q in p.partnerships
            ),
        }
    return people


def _vital(event):
    if event is None:
        return None
    extra = event.extra or {}
    cite = extra.get("cite")
    return (event.date, event.place, extra.get("note"), tuple([cite] if isinstance(cite, str) else cite or ()))


def reimport(tree, tmp_path):
    text, _ = export_gedcom(tree, today=TODAY)
    nodes, _ = parse_nodes(text)
    result = import_nodes(nodes)
    folder = tmp_path / "again"
    folder.mkdir()
    (folder / "site.yml").write_text("title: T\nschema_version: 3\n", encoding="utf-8")
    write_import_family(result, folder, text.encode("utf-8"), "export.ged")
    again, issues = load_tree(folder)
    assert not [i for i in issues if i.severity == "error"], issues
    return again, text


def test_a_family_survives_export_then_import(tmp_path, write_family):
    folder = tmp_path / "orig"
    write_family(folder, FAMILY)
    original, _ = load_tree(folder)
    again, _ = reimport(original, tmp_path)
    before, after = shape(original), shape(again)
    assert set(before) == set(after)
    for name in before:
        assert before[name] == after[name], name


def _cli(*argv):
    assert main([str(a) for a in argv]) == 0


def test_import_export_import_gives_the_same_family_file(tmp_path, sample_ged):
    first, second = tmp_path / "first", tmp_path / "second"
    _cli("init", "--dir", first)
    _cli("import-gedcom", sample_ged, "--dir", first, "-a")
    exported = tmp_path / "round.ged"
    _cli("export-gedcom", "--dir", first, "--out", exported)
    _cli("init", "--dir", second)
    _cli("import-gedcom", exported, "--dir", second, "-a")
    assert (second / "family.yml").read_text(encoding="utf-8") == (first / "family.yml").read_text(encoding="utf-8")
    again = tmp_path / "again.ged"
    _cli("export-gedcom", "--dir", second, "--out", again)
    assert again.read_text(encoding="utf-8") == exported.read_text(encoding="utf-8")


def test_the_lines_the_importer_set_aside_survive_a_round_trip(tmp_path):
    ged = tmp_path / "x.ged"
    ged.write_text(
        "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME A /B/\n1 SEX X\n1 _MYTAG hello\n2 NOTE deep\n0 TRLR\n", encoding="utf-8"
    )
    first, second = tmp_path / "first", tmp_path / "second"
    _cli("init", "--dir", first)
    _cli("import-gedcom", ged, "--dir", first, "-a")
    out = tmp_path / "o.ged"
    _cli("export-gedcom", "--dir", first, "--out", out)
    assert "1 _MYTAG hello\n2 NOTE deep" in out.read_text(encoding="utf-8")
    _cli("init", "--dir", second)
    _cli("import-gedcom", out, "--dir", second, "-a")
    assert (second / "archive" / "gedcom-extra.yml").read_text(encoding="utf-8") == (first / "archive" / "gedcom-extra.yml").read_text(encoding="utf-8")
