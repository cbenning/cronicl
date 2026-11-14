from datetime import date

from cronicl.cli import main
from cronicl.core.gaps import find_gaps
from cronicl.core.model import Event
from cronicl.core.relations import build_relations


def test_gaps_lists_missing_facts_best_connected_first(make_tree):
    tree = make_tree([
        {"id": "a", "given": "Ann", "birth": Event(date="1900", place="Y"), "death": Event(date="1980")},
        {"id": "b", "given": "Bob", "parents": ["a"]},
        {"id": "c"},
        {"id": "d", "given": "Dee", "birth": Event(date="1850", place="Y"), "parents": ["a"]},
    ])
    gaps = find_gaps(tree, build_relations(tree), today=date(2026, 1, 1))
    assert [(g.id, g.missing) for g in gaps] == [
        ("a", ["parents"]),
        ("b", ["birth date", "birth place"]),
        ("d", ["death date"]),
        ("c", ["name", "birth date", "birth place", "parents"]),
    ]


def test_gaps_cli_on_an_empty_folder(tmp_path, capsys):
    assert main(["init", "--legacy-layout", "--dir", str(tmp_path / "fam")]) == 0
    capsys.readouterr()
    assert main(["gaps", "--dir", str(tmp_path / "fam")]) == 0
    assert capsys.readouterr().out == ""
