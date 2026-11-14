from cronicl.model import Event, Partnership
from cronicl.relations import CouplePartnership, build_relations, couple_id


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


def test_partnership_declared_on_one_side_applies_to_the_couple(make_tree):
    tree = make_tree(
        [named("a", partnerships=[Partnership("b", type="marriage", start="1975", place="Surrey, BC")]), named("b")]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].partnerships == [
        CouplePartnership(type="marriage", start="1975", place="Surrey, BC")
    ]
    assert rel.issues == []


def test_identical_partnerships_on_both_sides_merge(make_tree):
    tree = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1975", place="Surrey")]),
            named("b", partnerships=[Partnership("a", type="marriage", start="1975", place="Surrey")]),
        ]
    )
    rel = build_relations(tree)
    assert len(rel.couples["a+b"].partnerships) == 1
    assert rel.issues == []


def test_start_on_one_file_and_end_on_the_other_are_one_partnership(make_tree):
    tree = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1955")]),
            named("b", partnerships=[Partnership("a", end="1971", end_reason="divorce")]),
        ]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].partnerships == [
        CouplePartnership(type="marriage", start="1955", end="1971", end_reason="divorce")
    ]
    assert rel.couples["a+b"].ended is True
    assert rel.issues == []


def test_differing_place_warns_and_smallest_owner_wins(make_tree):
    tree = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1975", place="Surrey")]),
            named("b", partnerships=[Partnership("a", type="marriage", start="1975", place="Delta")]),
        ]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].partnerships[0].place == "Surrey"
    assert codes(rel) == ["W-PARTNERSHIP-CONFLICT"]


def test_remarriage_to_the_same_person_is_two_partnerships(make_tree):
    tree = make_tree(
        [
            named(
                "a",
                partnerships=[
                    Partnership("b", type="marriage", start="1970"),
                    Partnership("b", type="marriage", start="1950", end="1960", end_reason="divorce"),
                ],
            ),
            named("b"),
        ]
    )
    rel = build_relations(tree)
    got = rel.couples["a+b"].partnerships
    assert [(p.start, p.end) for p in got] == [("1950", "1960"), ("1970", None)]
    assert rel.couples["a+b"].ended is False  # the latest partnership is still going
    assert rel.issues == []


def test_different_types_with_different_starts_stay_separate_and_unknown_merges(make_tree):
    tree = make_tree(
        [
            named(
                "a",
                partnerships=[
                    Partnership("b", type="engagement", start="1949"),
                    Partnership("b", type="marriage", start="1950"),
                ],
            ),
            named("b", partnerships=[Partnership("a")]),
        ]
    )
    rel = build_relations(tree)
    assert [p.type for p in rel.couples["a+b"].partnerships] == ["engagement", "marriage"]
    assert rel.issues == []


def test_spouse_shorthand_has_no_partnership_data(make_tree):
    tree = make_tree([named("a", spouse=["b"]), named("b")])
    rel = build_relations(tree)
    assert rel.couples["a+b"].partnerships == []
    assert rel.couples["a+b"].ended is False


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
                  partnerships=[Partnership("spectre", type="marriage", start="1900")]),
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


def test_same_marriage_at_different_date_precision_is_one_partnership(make_tree):
    tree = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1975")]),
            named("b", partnerships=[Partnership("a", type="marriage", start="1975-06-20", end="1990")]),
        ]
    )
    rel = build_relations(tree)
    assert rel.couples["a+b"].partnerships == [
        CouplePartnership(type="marriage", start="1975-06-20", end="1990")
    ]
    assert rel.issues == []


def test_approximate_year_and_exact_date_are_one_partnership_but_other_months_are_not(make_tree):
    same = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="~1975")]),
            named("b", partnerships=[Partnership("a", type="marriage", start="1975-06-20")]),
        ]
    )
    assert len(build_relations(same).couples["a+b"].partnerships) == 1
    apart = make_tree(
        [
            named("a", partnerships=[Partnership("b", type="marriage", start="1975-06")]),
            named("b", partnerships=[Partnership("a", type="marriage", start="1975-07")]),
        ]
    )
    assert len(build_relations(apart).couples["a+b"].partnerships) == 2
