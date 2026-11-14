import subprocess

import pytest

from cronicl.cli import main
from cronicl.core.migrate import apply_migration, plan_migration
from cronicl.core.store import load_tree


def run(*argv):
    return main([str(a) for a in argv])


def old_folder(tmp_path, write, people, site="title: T\nschema_version: 2\nprivacy:\n  living: full\n  id_salt: abc\n"):
    write(tmp_path, "site.yml", site)
    for pid, text in people.items():
        write(tmp_path, f"people/{pid}.md", f"---\nid: {pid}\n{text}---\n")
    return tmp_path


def migrate(tmp_path, *extra):
    return run("migrate", "--dir", tmp_path, "--allow-dirty", *extra)


def loaded(tmp_path):
    tree, issues = load_tree(tmp_path)
    assert [i for i in issues if i.severity == "error"] == [], issues
    return tree


def test_preview_writes_nothing_and_apply_moves_the_old_files_intact(tmp_path, write, capsys):
    old_folder(tmp_path, write, {"a": "name: A One\nbirth: ~1850\n", "b": "name: B Two\nparents: [a]\n"})
    before = {p.name: p.read_bytes() for p in (tmp_path / "people").glob("*.md")}
    assert migrate(tmp_path) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and not (tmp_path / "family.yml").exists() and (tmp_path / "people").is_dir()
    assert migrate(tmp_path, "--apply") == 0
    assert (tmp_path / "family.yml").is_file() and not (tmp_path / "people").exists()
    assert {p.name: p.read_bytes() for p in (tmp_path / "archive" / "people-md").glob("*.md")} == before
    assert "schema_version: 3" in (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert "privacy:" in (tmp_path / "site.yml").read_text(encoding="utf-8") and "id_salt: abc" in (tmp_path / "site.yml").read_text(encoding="utf-8")


def test_refusals(tmp_path, write):
    old_folder(tmp_path, write, {"a": "name: A\nparents: [ghost]\n"})
    assert migrate(tmp_path, "--apply") == 2  # the old data has an error
    assert (tmp_path / "people").is_dir()
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\n---\n")
    assert migrate(tmp_path, "--apply") == 0
    assert migrate(tmp_path, "--apply") == 2  # already migrated: family.yml exists
    assert run("migrate", "--dir", tmp_path.parent / "nothing-here") == 2


def test_a_dirty_git_tree_is_refused_unless_allowed(tmp_path, write):
    old_folder(tmp_path, write, {"a": "name: A\n"})
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    assert run("migrate", "--dir", tmp_path, "--apply") == 2
    assert run("migrate", "--dir", tmp_path, "--apply", "--allow-dirty") == 0


def test_names_sex_dates_and_the_living_false_rule(tmp_path, write):
    old_folder(
        tmp_path,
        write,
        {
            "a": "name:\n  given: Ada\n  surname: Alder\nsex: F\nbirth: ~1850\ndeath:\n  date: 1900\n  place: Leeds, England\n",
            "b": "name: Bo Blue\nsex: M\nliving: false\nbirth: 1860\n",
            "c": "name: Cy Cyan\nliving: false\ndeath: 1950\n",
            "d": "name: Di Dune\nliving: true\nbirth: 1990\n",
        },
    )
    assert migrate(tmp_path, "--apply") == 0
    tree = loaded(tmp_path)
    a, b, c, d = (tree.people[x] for x in "abcd")
    assert (a.given, a.surname, a.sex, a.birth.date, a.death.place) == ("Ada", "Alder", "F", "ABT 1850", "Leeds, England")
    assert b.sex == "M" and b.death.date == "unknown" and b.living is None
    assert c.death.date == "1950" and c.living is None
    assert d.living is True and d.death is None
    assert "living: false" not in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_children_and_spouse_declared_on_one_side_become_parents_and_couple_records(tmp_path, write):
    old_folder(
        tmp_path,
        write,
        {
            "mum": "name: Mum M\nchildren: [kid]\nspouse: [dad]\n",
            "dad": "name: Dad D\n",
            "kid": "name: Kid K\n",
            "x": "name: X Ex\nspouse: [y]\n",
            "y": "name: Y Why\n",
        },
    )
    assert migrate(tmp_path, "--apply") == 0
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    tree = loaded(tmp_path)
    assert tree.people["kid"].parents == ["mum"]  # only `mum` named the child
    assert "children:" not in text and "spouse:" not in text
    assert "x + y: {}" in text and "dad + mum: {}" in text  # childless-by-record couples keep a record
    assert tree.people["x"].spouse == ["y"]


@pytest.mark.parametrize(
    "partnership, expected_events",
    [
        ("- with: b\n    type: marriage\n    start: 1900-05\n    place: Leeds\n    note: n\n", ["marriage"]),
        ("- with: b\n    type: marriage\n    start: 1900\n    end: 1910\n    end_reason: divorce\n", ["marriage", "divorce"]),
        ("- with: b\n    type: marriage\n    start: 1900\n    end: 1910\n    end_reason: annulment\n", ["marriage", "annulment"]),
        ("- with: b\n    type: engagement\n    start: 1900\n    end: 1901\n    end_reason: separation\n", ["engagement", "separation"]),
        ("- with: b\n    type: civil-union\n    start: 1900\n", ["civil-union"]),
        ("- with: b\n    type: partnership\n    start: 1900\n    end: unknown\n", ["partnership", "end"]),
        ("- with: b\n    start: 1900\n", ["partnership"]),
        ("- with: b\n    type: marriage\n    start: 1900\n    end: 1910\n", ["marriage", "end"]),
    ],
)
def test_each_partnership_shape_becomes_couple_events(tmp_path, write, partnership, expected_events):
    old_folder(tmp_path, write, {"a": f"name: A One\npartnerships:\n  {partnership}", "b": "name: B Two\n"})
    assert migrate(tmp_path, "--apply") == 0
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    tree = loaded(tmp_path)
    (partnership_obj, *rest) = tree.people["a"].partnerships
    assert not rest
    types = [line.split("type: ")[1].split(",")[0].split("}")[0] for line in text.splitlines() if "- {type: " in line and "residence" not in line]
    assert types == expected_events


def test_remarriage_and_both_sides_declaring_the_same_partnership_merge_like_the_site_did(tmp_path, write):
    old_folder(
        tmp_path,
        write,
        {
            "a": "name: A One\npartnerships:\n  - with: b\n    type: marriage\n    start: 1900\n    end: 1905\n    end_reason: divorce\n  - with: b\n    type: marriage\n    start: 1910\n",
            "b": "name: B Two\nmarriages:\n  - with: a\n    date: 1900\n    place: Leeds\n",
        },
    )
    assert migrate(tmp_path, "--apply") == 0
    tree = loaded(tmp_path)
    parts = tree.people["a"].partnerships
    assert [(p.start, p.end, p.end_reason, p.place) for p in parts] == [("1900", "1905", "divorce", "Leeds"), ("1910", None, None, None)]
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert text.count("a + b:") == 1


def test_events_spans_cites_refs_extras_and_bodies(tmp_path, write):
    old_folder(
        tmp_path,
        write,
        {
            "a": "name: A One\ngallery_id: a-one\ngedcom_id: \"@I1@\"\ngedcom_extra: |\n  1 OBJE\n  2 FILE x.jpg\nx-note: hi\nflavour: odd\n"
            "events:\n  - type: residence\n    start: 1900\n    end: 1910\n    place: Leeds\n  - type: occupation\n    value: Cook\n    cite: [c1, c2]\n"
            "  - type: immigration\n    date: ~1905\n",
        },
    )
    path = tmp_path / "people" / "a.md"
    path.write_text(path.read_text(encoding="utf-8") + "Bio line one.\n\nBio: line two.\n", encoding="utf-8")
    assert migrate(tmp_path, "--apply") == 0
    tree = loaded(tmp_path)
    a = tree.people["a"]
    assert (a.events[0].start, a.events[0].end) == ("1900", "1910")
    assert a.events[1].cite == ["c1", "c2"] and a.events[2].date == "ABT 1905"
    assert (a.gallery_id, a.gedcom_id) == ("a-one", "@I1@")
    assert a.extra == {"x-note": "hi", "flavour": "odd"}
    assert a.body == "Bio line one.\n\nBio: line two."
    extra = (tmp_path / "archive" / "gedcom-extra.yml").read_text(encoding="utf-8")
    assert "a: |" in extra and "1 OBJE" in extra and "gedcom_extra" not in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_the_preview_lists_conflicts_and_dropped_data(tmp_path, write, capsys):
    old_folder(
        tmp_path,
        write,
        {
            "a": "name: A One\npartnerships:\n  - with: b\n    type: marriage\n    start: 1900\n    place: Leeds\n",
            "b": "name: B Two\npartnerships:\n  - with: a\n    type: marriage\n    start: 1900\n    place: York\n",
        },
    )
    assert migrate(tmp_path) == 0
    out = capsys.readouterr().out
    assert "differing place" in out and "Leeds" in out and "York" in out


def test_the_migrated_folder_passes_check_and_builds(tmp_path, write, capsys):
    old_folder(tmp_path, write, {"a": "name: A One\nbirth: 1850\n", "b": "name: B Two\nparents: [a]\n"})
    assert migrate(tmp_path, "--apply") == 0
    capsys.readouterr()
    assert run("check", "--dir", tmp_path) == 0
    assert run("build", "--dir", tmp_path, "--out", tmp_path / "out") == 0


def test_overlapping_partnerships_of_different_kinds_are_noted(tmp_path, write, capsys):
    old_folder(
        tmp_path,
        write,
        {
            "a": "name: A One\npartnerships:\n  - with: b\n    type: civil-union\n    start: 1920\n    end: 1921\n    end_reason: annulment\n",
            "b": "name: B Two\nmarriages:\n  - with: a\n    date: 1920\n    place: Vancouver\n",
        },
    )
    assert migrate(tmp_path) == 0
    out = capsys.readouterr().out
    assert "a + b: the partnerships overlap" in out and "latest open partnership" in out


def test_a_clean_migration_has_no_notes(tmp_path, write, capsys):
    old_folder(tmp_path, write, {"a": "name: A One\npartnerships:\n  - with: b\n    type: marriage\n    start: 1900\n    end: 1910\n    end_reason: divorce\n", "b": "name: B Two\n"})
    assert migrate(tmp_path) == 0
    assert "NOTE" not in capsys.readouterr().out


def test_a_legacy_span_with_an_approximate_end_migrates_to_a_readable_span(tmp_path):
    from cronicl.core.dates import parse_span

    (tmp_path / "people").mkdir()
    (tmp_path / "site.yml").write_text("title: T\nschema_version: 2\n", encoding="utf-8")
    (tmp_path / "people" / "a.md").write_text(
        "---\nid: a\nname: A\nevents:\n  - type: occupation\n    start: 1900\n    end: '~1910'\n---\n", encoding="utf-8"
    )
    plan = plan_migration(tmp_path)
    apply_migration(tmp_path, plan)
    text = (tmp_path / "family.yml").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if "FROM" in l)
    value = line.split("date:")[1].strip(" },")
    assert parse_span(value) is not None, line
