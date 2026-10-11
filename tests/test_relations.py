from famsite.model import Event, Marriage
from famsite.relations import build_relations, couple_id


def named(pid, **kw):
    return {"id": pid, "given": pid, **kw}


def codes(rel):
    return sorted(i.code for i in rel.issues)


def test_couple_id():
    assert couple_id(["smith-bob", "jones-jane"]) == "jones-jane+smith-bob"
    assert couple_id(["smith-bob"]) == "smith-bob+"


def test_up_reference_creates_a_birth_couple(make_tree):
    tree = make_tree([named("a"), named("b"), named("c", parents=["a", "b"])])
    rel = build_relations(tree)
    assert rel.parents == {"a": [], "b": [], "c": ["a", "b"]}
    assert rel.birth_couple == {"c": "a+b"}
    assert rel.couples["a+b"].partners == ["a", "b"]
    assert rel.kids["a+b"] == ["c"]
    assert rel.couples_of["a"] == ["a+b"]
    assert rel.issues == []


def test_down_reference_is_merged(make_tree):
    # Review focus 3: only the parents declare the child.
    tree = make_tree([named("a", children=["c"]), named("b", children=["c"]), named("c")])
    rel = build_relations(tree)
    assert rel.parents["c"] == ["a", "b"]
    assert rel.birth_couple["c"] == "a+b"


def test_up_and_down_on_both_ends_do_not_duplicate(make_tree):
    tree = make_tree([named("a", children=["c"]), named("b"), named("c", parents=["a", "b"])])
    rel = build_relations(tree)
    assert rel.parents["c"] == ["a", "b"]
    assert rel.kids["a+b"] == ["c"]
    assert rel.issues == []


def test_single_parent_couple(make_tree):
    tree = make_tree([named("a"), named("c", parents=["a"])])
    rel = build_relations(tree)
    assert rel.birth_couple["c"] == "a+"
    assert rel.couples["a+"].partners == ["a"]


def test_half_siblings_share_a_parent(make_tree):
    tree = make_tree(
        [named("a"), named("b"), named("d"), named("c1", parents=["a", "b"]), named("c2", parents=["a", "d"])]
    )
    rel = build_relations(tree)
    assert rel.couples_of["a"] == ["a+b", "a+d"]
    assert rel.couples_of["b"] == ["a+b"]


def test_spouse_on_either_side_makes_a_childless_couple(make_tree):
    tree = make_tree([named("a", spouse=["b"]), named("b")])
    rel = build_relations(tree)
    assert rel.couples["a+b"].partners == ["a", "b"]
    assert rel.kids["a+b"] == []
    assert rel.couples_of["b"] == ["a+b"]


def test_marriage_declared_on_one_side_applies_to_the_couple(make_tree):
    tree = make_tree([named("a", marriages=[Marriage("b", "1975", "Surrey, BC")]), named("b")])
    rel = build_relations(tree)
    assert rel.couples["a+b"].marriage == Event(date="1975", place="Surrey, BC")
    assert rel.issues == []


def test_identical_marriages_on_both_sides_merge(make_tree):
    tree = make_tree(
        [
            named("a", marriages=[Marriage("b", "1975", "Surrey")]),
            named("b", marriages=[Marriage("a", "1975", "Surrey")]),
        ]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].marriage == Event(date="1975", place="Surrey")
    assert rel.issues == []


def test_conflicting_marriages_warn_and_smallest_owner_wins(make_tree):
    tree = make_tree(
        [
            named("a", marriages=[Marriage("b", "1975")]),
            named("b", marriages=[Marriage("a", "1976")]),
        ]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].marriage == Event(date="1975")
    assert codes(rel) == ["W-MARRIAGE-CONFLICT"]


def test_more_than_two_parents_warns_and_truncates(make_tree):
    tree = make_tree([named("a"), named("b"), named("d"), named("c", parents=["a", "b", "d"])])
    rel = build_relations(tree)
    assert rel.parents["c"] == ["a", "b"]
    assert codes(rel) == ["W-TOO-MANY-PARENTS"]


def test_down_declared_parents_come_after_declared_parents(make_tree):
    tree = make_tree([named("a"), named("z", children=["c"]), named("c", parents=["a"])])
    rel = build_relations(tree)
    assert rel.parents["c"] == ["a", "z"]


def test_dangling_references_are_reported_and_ignored(make_tree):
    tree = make_tree(
        [
            named("a", parents=["ghost"], spouse=["phantom"], children=["nobody"],
                  marriages=[Marriage("spectre", "1900")]),
        ]
    )
    rel = build_relations(tree)
    assert codes(rel) == ["E-DANGLING-REF"] * 4
    assert rel.parents["a"] == []
    assert rel.couples == {}


def test_self_spouse_is_a_warning(make_tree):
    tree = make_tree([named("a", spouse=["a"])])
    rel = build_relations(tree)
    assert codes(rel) == ["W-SELF-REFERENCE"]
    assert rel.couples == {}


def test_self_parent_is_kept_so_check_can_report_the_cycle(make_tree):
    tree = make_tree([named("a", parents=["a"])])
    rel = build_relations(tree)
    assert rel.parents["a"] == ["a"]
