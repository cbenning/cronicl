from pathlib import Path

from famsite.check import check_tree, has_errors
from famsite.issues import Issue
from famsite.model import Event, Marriage


def codes(issues):
    return sorted(i.code for i in issues)


def named(pid, **kw):
    return {"id": pid, "given": pid.title(), "surname": "Test", **kw}


def test_clean_tree_has_no_issues(make_tree):
    tree = make_tree([named("a"), named("b"), named("c", parents=["a", "b"], birth=Event(date="1990"))])
    assert check_tree(tree) == []


def test_dangling_parent(make_tree):
    tree = make_tree([named("a", parents=["nope"])])
    assert codes(check_tree(tree)) == ["E-DANGLING-REF"]


def test_dangling_spouse_and_marriage(make_tree):
    tree = make_tree([named("a", spouse=["ghost"], marriages=[Marriage("phantom")])])
    assert codes(check_tree(tree)) == ["E-DANGLING-REF", "E-DANGLING-REF"]


def test_invalid_id(make_tree):
    tree = make_tree([named("Bad_Id")])
    assert "E-INVALID-ID" in codes(check_tree(tree))


def test_filename_drift_is_a_warning(make_tree):
    tree = make_tree([named("smith-bob", path=Path("/d/people/bob.md"))])
    issues = check_tree(tree)
    assert codes(issues) == ["W-FILENAME-DRIFT"]
    assert not has_errors(issues)


def test_matching_filename_is_clean(make_tree):
    tree = make_tree([named("smith-bob", path=Path("/d/people/smith-bob.md"))])
    assert check_tree(tree) == []


def test_missing_name_is_a_warning(make_tree):
    tree = make_tree([{"id": "x"}])
    assert codes(check_tree(tree)) == ["W-NO-NAME"]


def test_unparsable_dates_are_warnings(make_tree):
    tree = make_tree(
        [
            named("a", birth=Event(date="BET 1900 AND 1910"), marriages=[Marriage("b", "sometime")]),
            named("b"),
        ]
    )
    assert codes(check_tree(tree)) == ["W-DATE-UNPARSED", "W-DATE-UNPARSED"]


def test_person_who_is_their_own_parent_is_a_cycle(make_tree):
    # Review focus 5.
    tree = make_tree([named("a", parents=["a"])])
    assert "E-CYCLE" in codes(check_tree(tree))


def test_longer_cycle(make_tree):
    tree = make_tree([named("a", parents=["b"]), named("b", parents=["a"])])
    issues = check_tree(tree)
    assert "E-CYCLE" in codes(issues)
    assert has_errors(issues)


def test_down_declared_cycle_is_found(make_tree):
    tree = make_tree([named("a", children=["b"]), named("b", children=["a"])])
    assert "E-CYCLE" in codes(check_tree(tree))


def test_relation_warnings_are_passed_through(make_tree):
    tree = make_tree([named("a"), named("b"), named("d"), named("c", parents=["a", "b", "d"])])
    assert codes(check_tree(tree)) == ["W-TOO-MANY-PARENTS"]


def test_load_issues_are_included_and_errors_detected(make_tree):
    tree = make_tree([named("a")])
    issues = check_tree(tree, [Issue("E-BAD-FRONTMATTER", "boom", "people/x.md")])
    assert has_errors(issues)
    assert codes(issues) == ["E-BAD-FRONTMATTER"]
