from cronicl.core.fix import apply_plan, plan_fix
from cronicl.core.store import load_tree


def names(directory):
    return sorted(p.name for p in directory.glob("*.md"))


def test_renames_file_to_match_pinned_id(tmp_path, write):
    write(tmp_path, "people/bob.md", "---\nid: smith-bob\nname: Bob Smith\n---\n")
    plan = plan_fix(tmp_path)
    assert not plan.empty
    apply_plan(plan)
    assert names(tmp_path / "people") == ["smith-bob.md"]
    tree, _ = load_tree(tmp_path)
    assert tree.people["smith-bob"].given == "Bob"


def test_pins_missing_id_from_stem(tmp_path, write):
    write(tmp_path, "people/Smith Bob.md", "---\nname: Bob Smith\n---\nBio\n")
    apply_plan(plan_fix(tmp_path))
    assert names(tmp_path / "people") == ["smith-bob.md"]
    text = (tmp_path / "people" / "smith-bob.md").read_text(encoding="utf-8")
    assert "id: smith-bob" in text
    assert "Bio" in text


def test_collision_between_implicit_ids_is_deterministic(tmp_path, write):
    write(tmp_path, "people/Bob Smith.md", "---\nname: Upper Smith\n---\n")
    write(tmp_path, "people/bob-smith.md", "---\nname: Lower Smith\n---\n")
    apply_plan(plan_fix(tmp_path))
    assert names(tmp_path / "people") == ["bob-smith-2.md", "bob-smith.md"]
    tree, _ = load_tree(tmp_path)
    assert tree.people["bob-smith"].given == "Upper"
    assert tree.people["bob-smith-2"].given == "Lower"


def test_invalid_explicit_id_is_normalized_and_every_reference_kind_rewritten(tmp_path, write):
    write(tmp_path, "people/smith_bob.md", "---\nid: Smith_Bob\nname: Bob Smith\n---\n")
    write(
        tmp_path,
        "people/amy.md",
        "---\nname: Amy Smith\nparents:\n  - Smith_Bob\nspouse:\n  - Smith_Bob\n"
        "children:\n  - Smith_Bob\nmarriages:\n  - with: Smith_Bob\n    date: 1990\n---\n",
    )
    apply_plan(plan_fix(tmp_path))
    tree, issues = load_tree(tmp_path)
    amy = tree.people["amy"]
    assert "smith-bob" in tree.people
    assert amy.parents == ["smith-bob"]
    assert amy.spouse == ["smith-bob"]
    assert amy.children == ["smith-bob"]
    assert [m.with_id for m in amy.partnerships] == ["smith-bob"]
    assert amy.partnerships[0].start == "1990"


def test_references_to_a_collision_renamed_file_follow_the_stem_alias(tmp_path, write):
    write(tmp_path, "people/Bob Smith.md", "---\nname: Upper Smith\n---\n")
    write(tmp_path, "people/amy.md", "---\nname: Amy\nparents: [Bob Smith]\n---\n")
    apply_plan(plan_fix(tmp_path))
    tree, _ = load_tree(tmp_path)
    assert tree.people["amy"].parents == ["bob-smith"]


def test_valid_id_never_changes_even_if_name_changes(tmp_path, write):
    write(tmp_path, "people/old-name.md", "---\nid: smith-bob\nname: Robert Jones\n---\n")
    apply_plan(plan_fix(tmp_path))
    tree, _ = load_tree(tmp_path)
    assert list(tree.people) == ["smith-bob"]
    assert tree.people["smith-bob"].surname == "Jones"


def test_duplicate_explicit_ids_are_reported_not_touched(tmp_path, write):
    write(tmp_path, "people/a.md", "---\nid: smith-bob\nname: First\n---\n")
    write(tmp_path, "people/b.md", "---\nid: smith-bob\nname: Second\n---\n")
    plan = plan_fix(tmp_path)
    assert plan.empty
    assert [i.code for i in plan.unresolved] == ["E-DUPLICATE-ID", "E-DUPLICATE-ID"]


def test_fix_does_not_move_relationships_between_files(tmp_path, write):
    write(tmp_path, "people/dad.md", "---\nid: dad\nname: Dad\nchildren: [kid]\n---\n")
    write(tmp_path, "people/kid.md", "---\nid: kid\nname: Kid\n---\n")
    apply_plan(plan_fix(tmp_path))
    tree, _ = load_tree(tmp_path)
    assert tree.people["dad"].children == ["kid"]
    assert tree.people["kid"].parents == []


def test_fix_is_idempotent_and_keeps_unknown_keys(tmp_path, write):
    write(tmp_path, "people/Bob Smith.md", "---\nname: Bob Smith\nbirth: 1950\n---\nBio\n")
    write(tmp_path, "people/amy.md", "---\nname: Amy Smith\nunknown_key: kept\n---\n")
    apply_plan(plan_fix(tmp_path))
    assert plan_fix(tmp_path).empty
    tree, _ = load_tree(tmp_path)
    assert tree.people["amy"].extra == {"unknown_key": "kept"}


def test_broken_frontmatter_is_reported_not_rewritten(tmp_path, write):
    write(tmp_path, "people/bad.md", "---\nname: [unclosed\n---\n")
    plan = plan_fix(tmp_path)
    assert plan.empty
    assert [i.code for i in plan.unresolved] == ["E-BAD-FRONTMATTER"]


def test_fix_migrates_marriages_to_partnerships_and_bumps_schema_version(tmp_path, write):
    write(tmp_path, "site.yml", "title: T\nschema_version: 1\n")
    write(tmp_path, "people/a.md", "---\nid: a\nname: A\nmarriages:\n  - with: b\n    date: 1975\n---\n")
    write(tmp_path, "people/b.md", "---\nid: b\nname: B\n---\n")
    apply_plan(plan_fix(tmp_path))
    text = (tmp_path / "people" / "a.md").read_text(encoding="utf-8")
    assert "partnerships:" in text and "marriages:" not in text
    assert "type: marriage" in text and "start: 1975" in text and "date:" not in text
    assert "schema_version: 2" in (tmp_path / "site.yml").read_text(encoding="utf-8")
    assert plan_fix(tmp_path).empty  # idempotent
