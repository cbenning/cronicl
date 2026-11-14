from pathlib import Path

from famsite.check import check_tree, has_errors
from famsite.issues import Issue
from famsite.model import Event, Partnership
from famsite.store import load_tree


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
    tree = make_tree([named("a", spouse=["ghost"], partnerships=[Partnership("phantom")])])
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
            named("a", birth=Event(date="BET 1900 AND 1910"), partnerships=[Partnership("b", type="marriage", start="sometime")]),
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


def test_partnership_dates_are_checked(make_tree):
    tree = make_tree(
        [named("a", partnerships=[Partnership("b", type="marriage", start="sometime", end="later")]), named("b")]
    )
    assert codes(check_tree(tree)) == ["W-DATE-UNPARSED", "W-DATE-UNPARSED"]


def test_end_unknown_is_not_a_date_problem(make_tree):
    tree = make_tree([named("a", partnerships=[Partnership("b", type="marriage", end="unknown")]), named("b")])
    assert codes(check_tree(tree)) == []


def test_end_before_start_warns(make_tree):
    tree = make_tree(
        [named("a", partnerships=[Partnership("b", type="marriage", start="1990", end="1980")]), named("b")]
    )
    assert codes(check_tree(tree)) == ["W-END-BEFORE-START"]


def test_end_before_start_is_found_across_both_files(make_tree):
    tree = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1990")]),
            named("b", partnerships=[Partnership("a", end="1980")]),
        ]
    )
    assert codes(check_tree(tree)) == ["W-END-BEFORE-START"]


def test_unknown_type_and_reason_warn_but_are_kept(make_tree):
    tree = make_tree(
        [named("a", partnerships=[Partnership("b", type="handfasting", end="1990", end_reason="drifted")]), named("b")]
    )
    assert codes(check_tree(tree)) == ["W-END-REASON-UNKNOWN", "W-PARTNERSHIP-TYPE-UNKNOWN"]


def test_unknown_home_is_reported(make_tree):
    tree = make_tree([{"id": "a", "given": "A"}])
    tree.site = {"home": "nobody"}
    assert "W-HOME-UNKNOWN" in [i.code for i in check_tree(tree)]


def test_portrait_checks(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\n")
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "big.png").write_bytes(b"0" * 1_000_001)
    (tmp_path / "media" / "doc.svg").write_bytes(b"<svg/>")
    (tmp_path / "secret.jpg").write_bytes(b"s")
    (tmp_path / "media" / "link.jpg").symlink_to(tmp_path / "secret.jpg")
    for pid, value in (("a", "../x.jpg"), ("b", "gone.jpg"), ("c", "big.png"), ("d", "doc.svg"), ("e", "link.jpg")):
        write(tmp_path, f"people/{pid}.md", f"---\nname: {pid}\nportrait: {value}\n---\n")
    tree, load_issues = load_tree(tmp_path)
    codes_by_path = {i.path: i.code for i in check_tree(tree, load_issues) if "PORTRAIT" in i.code}
    assert codes_by_path == {
        "people/a.md": "E-PORTRAIT-PATH", "people/b.md": "W-PORTRAIT-MISSING", "people/c.md": "W-PORTRAIT-LARGE",
        "people/d.md": "W-PORTRAIT-TYPE", "people/e.md": "E-PORTRAIT-PATH",
    }


def test_event_checks(make_tree):
    from famsite.model import LifeEvent

    tree = make_tree([{"id": "a", "given": "A", "events": [
        LifeEvent(type="", value="x"),
        LifeEvent(type="residence", start="1960", end="1950"),
        LifeEvent(type="burial", date="soon"),
        LifeEvent(type="moved-house", date="1940"),
    ]}])
    assert sorted(i.code for i in check_tree(tree)) == ["W-DATE-UNPARSED", "W-END-BEFORE-START", "W-EVENT-NO-TYPE"]


def test_bad_site_links_are_reported(make_tree):
    tree = make_tree([{"id": "a", "given": "A"}])
    tree.site = {"edit_url": "https://example.org/x", "contact": "javascript:alert(1)"}
    assert [i.code for i in check_tree(tree)].count("W-BAD-LINK") == 2
