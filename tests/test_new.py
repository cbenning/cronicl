import pytest

from cronicl.checks import check_all as check_tree
from cronicl.cli import main
from cronicl.core.store import load_tree


@pytest.fixture
def root(tmp_path, write):
    root = tmp_path / "fam"
    assert main(["init", "--legacy-layout", "--dir", str(root)]) == 0
    write(root, "people/smith-john.md", "---\nid: smith-john\nname:\n  given: John\n  surname: Smith\n---\n")
    write(root, "people/brown-mary.md", "---\nid: brown-mary\nname:\n  given: Mary\n  surname: Brown\n---\n")
    write(root, "people/smith-amy.md", "---\nid: smith-amy\nname:\n  given: Amy\n  surname: Smith\n---\n")
    return root


BOB = ["--given", "Bob", "--surname", "Smith", "--birth", "1950-03-12", "--birth-place", "Vancouver, BC",
       "--parents", "smith-john", "brown-mary"]


def test_new_previews_then_writes(root, capsys):
    assert main(["new", "--dir", str(root), *BOB]) == 0
    out = capsys.readouterr().out
    assert "people/smith-bob.md" in out and "given: Bob" in out and "dry run" in out
    assert not (root / "people/smith-bob.md").exists()
    assert main(["new", "--dir", str(root), *BOB, "-a"]) == 0
    tree, issues = load_tree(root)
    bob = tree.people["smith-bob"]
    assert (bob.given, bob.surname, bob.birth.date, bob.birth.place, bob.parents) == (
        "Bob", "Smith", "1950-03-12", "Vancouver, BC", ["smith-john", "brown-mary"])
    assert not [i for i in check_tree(tree, issues) if i.severity == "error"]
    assert main(["new", "--dir", str(root), *BOB, "-a"]) == 0  # a second Bob Smith gets his own id
    assert len([pid for pid in load_tree(root)[0].people if pid.startswith("smith-bob")]) == 2


@pytest.mark.parametrize("args, message", [
    (["--given", "X", "--parents", "nobody"], "unknown person id"),
    (["--given", "X", "--parents", "smith-john", "smith-john"], "listed twice"),
    (["--given", "X", "--spouse", "smith-john", "--children", "smith-john"], "listed twice"),
    (["--given", "X", "--parents", "smith-john", "brown-mary", "smith-amy"], "at most two parents"),
    (["--given", "X", "--birth", "March 1950"], "not a date"),
    ([], "--given or --surname"),
])
def test_new_refuses_bad_input_and_writes_nothing(root, capsys, args, message):
    before = sorted(p.name for p in (root / "people").iterdir())
    assert main(["new", "--dir", str(root), *args, "-a"]) == 2
    assert message in capsys.readouterr().err
    assert sorted(p.name for p in (root / "people").iterdir()) == before


def test_new_rejects_an_unknown_sex(root):
    with pytest.raises(SystemExit):
        main(["new", "--dir", str(root), "--given", "X", "--sex", "Q", "-a"])


def test_new_with_a_name_that_slugs_to_nothing(root):
    assert main(["new", "--dir", str(root), "--given", "\u738b", "-a"]) == 0
    tree, issues = load_tree(root)
    assert [p.given for p in tree.people.values() if p.given == "\u738b"] == ["\u738b"]
    assert not [i for i in check_tree(tree, issues) if i.severity == "error"]


def test_new_outside_a_cronicl_folder(tmp_path, capsys):
    assert main(["new", "--dir", str(tmp_path), "--given", "X", "-a"]) == 2
    assert "cronicl init" in capsys.readouterr().err and not (tmp_path / "people").exists()


def test_new_never_overwrites_an_existing_file(root, write):
    write(root, "people/doe-jane.md", "---\nid: someone-else\nname: Somebody\n---\nPrecious notes.\n")
    assert main(["new", "--dir", str(root), "--given", "Jane", "--surname", "Doe", "-a"]) == 0
    assert "Precious notes." in (root / "people/doe-jane.md").read_text(encoding="utf-8")
    assert (root / "people/doe-jane-2.md").exists()
