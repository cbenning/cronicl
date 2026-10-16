import re

from famsite.layout import compute_layout
from famsite.svgviews import lifeline_svg, tree_svg, wrap_name


def row(year, etype="birth", role="self", text="born", month=None, day=None):
    return {"id": f"{etype}:{year}", "type": etype, "role": role, "text": text, "year": year, "month": month, "day": day}


def test_wrap_name_fits_two_lines_and_ellipsizes():
    assert wrap_name("Bob Smith") == ["Bob Smith"]
    assert wrap_name("Maude Sylvie Marnie Ellsworth") == ["Maude Sylvie Marnie", "Ellsworth"]
    lines = wrap_name("Jeremiah Humphrey Alexander Ashby Herbert")
    assert len(lines) == 2 and lines[1].endswith("…") and all(len(x) <= 20 for x in lines)
    assert wrap_name("Pneumonoultramicroscopicsilico")[0].endswith("…")
    assert wrap_name("") == [""]


def test_lifeline_needs_two_dated_events():
    assert lifeline_svg([row(1950)], "x", "Ann") == ""
    assert lifeline_svg([], "x", "Ann") == ""


def test_lifeline_marks_own_and_relative_events_and_escapes():
    rows = [row(1950), row(1975, "marriage", "self", "married <Bo>"), row(1990, "death", "parent", "Pat died")]
    svg = lifeline_svg(rows, "../../index.html#/timeline/a", 'Ann "A" <x>')
    assert svg.count("<circle") == 3
    assert svg.count("self") >= 2 and "rel" in svg
    assert "&lt;Bo&gt;" in svg and "<Bo>" not in svg
    assert 'aria-label="Lifeline of Ann &quot;A&quot; &lt;x&gt;"' in svg
    assert 'href="../../index.html#/timeline/a"' in svg
    assert "1950" in svg and "1990" in svg


def people_of(tree):
    return {pid: {"name": p.display_name, "years": ""} for pid, p in tree.people.items()}


def test_tree_svg_links_every_node_and_marks_current(make_tree):
    tree = make_tree(
        [
            {"id": "a", "given": "Ann", "surname": "O'Neil <b>"},
            {"id": "b", "given": "Bo"},
            {"id": "c", "given": "Cy", "parents": ["a", "b"]},
        ]
    )
    svg = tree_svg(compute_layout(tree), people_of(tree), "c", lambda pid: f"../{pid}/", "Tree of Cy")
    assert svg.count("<a ") == 3
    assert 'href="../a/"' in svg and 'href="../c/"' in svg
    assert 'class="node current"' in svg
    assert "&lt;b&gt;" in svg and "<b>" not in svg


def test_tree_svg_is_omitted_for_a_lone_person(make_tree):
    tree = make_tree([{"id": "a", "given": "Ann"}])
    assert tree_svg(compute_layout(tree), people_of(tree), "a", lambda p: p, "t") == ""


def test_very_deep_trees_still_render_a_link_per_node(make_tree):
    people = [{"id": "p0", "given": "P0"}]
    for i in range(1, 60):
        people.append({"id": f"p{i}", "given": f"P{i}", "parents": [f"p{i - 1}"]})
    tree = make_tree(people)
    svg = tree_svg(compute_layout(tree), people_of(tree), "p30", lambda pid: f"../{pid}/", "t")
    assert len(re.findall(r"<a ", svg)) == 60


def test_no_name_line_exceeds_the_character_budget(make_tree):
    tree = make_tree(
        [
            {"id": "a", "given": "Jeremiah Humphrey Alexander", "surname": "Ashby-Hendrikson"},
            {"id": "b", "given": "Bo"},
            {"id": "c", "given": "Cy", "parents": ["a", "b"]},
        ]
    )
    svg = tree_svg(compute_layout(tree), people_of(tree), "a", lambda pid: pid, "t")
    texts = re.findall(r"<tspan[^>]*>([^<]*)</tspan>", svg)
    assert texts and all(len(t) <= 20 for t in texts)


def test_tree_svg_is_a_group_so_its_links_stay_in_the_accessibility_tree(make_tree):
    tree = make_tree([{"id": "a", "given": "Ann"}, {"id": "b", "given": "Bo", "parents": ["a"]}])
    svg = tree_svg(compute_layout(tree), people_of(tree), "a", lambda pid: pid, "Tree")
    assert 'role="group"' in svg and 'role="img"' not in svg
