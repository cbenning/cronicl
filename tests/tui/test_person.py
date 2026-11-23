import pytest

from conftest import FAMILY, drive, folder, highlight, option_texts, screen_name, texts

SIZES = [(80, 24), (120, 40)]
WITH_PROBLEM = FAMILY + "\nstrange-sam:\n  name: {given: Sam, surname: Strange}\n  sex: M\n  birth: 1950\n"


def head(app):
    from textual.widgets import Static

    return str(app.screen.query_one("#person-head", Static).content)


@pytest.mark.parametrize("size", SIZES)
def test_the_person_screen_shows_a_header_and_the_record_as_rows(tmp_path, size):
    folder(tmp_path)

    async def script(pilot, app):
        app.open_person("lovelace-ada")
        await pilot.pause()
        return screen_name(app), head(app), option_texts(app)

    name, header, rows = drive(tmp_path, script, size)
    assert name == "PersonScreen"
    assert "Augusta Ada Lovelace" in header and "1815–1852" in header and "lovelace-ada" in header and "family.yml" in header
    joined = "\n".join(rows)
    assert "given: Augusta Ada" in joined and "place: London, England" in joined and "George Byron" in joined


def test_family_lines_list_parents_partners_and_children(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        app.open_person("byron-george")
        await pilot.pause()
        george = "\n".join(option_texts(app))
        app.open_person("lovelace-ada")
        await pilot.pause()
        return george, "\n".join(option_texts(app))

    george, ada = drive(tmp_path, script)
    assert "Partners" in george and "Annabella Milbanke" in george and "m. 1815-01-02" in george
    assert "Children" in george and "Augusta Ada Lovelace" in george
    assert "Parents" in ada and "George Byron" in ada and "Annabella Milbanke" in ada


def test_enter_on_a_family_line_opens_that_person_and_escape_comes_back(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        app.open_person("lovelace-ada")
        await pilot.pause()
        await highlight(pilot, app, "George Byron  1788")
        await pilot.press("enter")
        await pilot.pause()
        second = head(app)
        await pilot.press("escape")
        await pilot.pause()
        return second, head(app)

    second, first = drive(tmp_path, script)
    assert "George Byron" in second and "Augusta Ada" in first


def test_a_partner_line_expands_the_couples_record_and_o_opens_the_partner(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        app.open_person("byron-george")
        await pilot.pause()
        await highlight(pilot, app, "Annabella Milbanke")
        await pilot.press("enter")
        await pilot.pause()
        expanded = "\n".join(option_texts(app))
        await pilot.press("enter")
        await pilot.pause()
        collapsed = "\n".join(option_texts(app))
        await pilot.press("o")
        await pilot.pause()
        return expanded, collapsed, head(app)

    expanded, collapsed, opened = drive(tmp_path, script)
    assert "type: marriage" in expanded and "place: Seaham, England" in expanded
    assert "type: marriage" not in collapsed
    assert "Annabella Milbanke" in opened


def test_an_expanded_partner_has_an_open_row_that_goes_to_the_partner(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        app.open_person("byron-george")
        await pilot.pause()
        await highlight(pilot, app, "Annabella Milbanke")
        await pilot.press("enter")
        await pilot.pause()
        rows = option_texts(app)
        await highlight(pilot, app, "Open Annabella Milbanke")
        await pilot.press("enter")
        await pilot.pause()
        return rows, head(app)

    rows, opened = drive(tmp_path, script)
    assert any("Open Annabella Milbanke" in row for row in rows)
    assert "Annabella Milbanke" in opened


def test_warnings_are_listed_and_enter_jumps_to_the_row(tmp_path):
    folder(tmp_path, family=WITH_PROBLEM)

    async def script(pilot, app):
        app.open_person("strange-sam")
        await pilot.pause()
        rows = option_texts(app)
        from textual.widgets import OptionList

        await highlight(pilot, app, "W-BAD-SEX")
        await pilot.press("enter")
        await pilot.pause()
        widget = app.screen.query_one("#record", OptionList)
        return rows, str(widget.get_option_at_index(widget.highlighted).prompt)

    rows, landed = drive(tmp_path, script)
    assert any("⚠" in r and "W-BAD-SEX" in r for r in rows)
    assert "sex" in landed and "M" in landed


def test_a_row_with_a_problem_is_marked(tmp_path):
    folder(tmp_path, family=WITH_PROBLEM)

    async def script(pilot, app):
        app.open_person("strange-sam")
        await pilot.pause()
        return option_texts(app)

    rows = drive(tmp_path, script)
    assert any("sex: M" in r and "⚠" in r for r in rows)


SOLO = FAMILY + """
solo-parent:
  name: {given: Solo, surname: Parent}

kid-one:
  name: {given: Kid, surname: One}
  parents: [solo-parent]

kid-two:
  name: {given: Kay, surname: Two}
  parents: [solo-parent]
"""


def test_a_single_parent_sees_their_children_on_their_own_screen(tmp_path):
    folder(tmp_path, family=SOLO)

    async def script(pilot, app):
        app.open_person("solo-parent")
        await pilot.pause()
        parent = "\n".join(option_texts(app))
        app.open_person("kid-one")
        await pilot.pause()
        return parent, "\n".join(option_texts(app))

    parent, kid = drive(tmp_path, script)
    assert "Children" in parent and "Kid One" in parent and "Kay Two" in parent
    assert "Partners" not in parent  # a lone parent has no partner line
    assert "Solo Parent" in kid and "Kay Two" in kid  # the siblings through the one parent


def test_a_child_added_in_the_tui_shows_under_a_parent_created_in_the_tui(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        from test_editors import type_text

        await pilot.press("ctrl+n")
        await pilot.pause()
        await type_text(pilot, "Pat")
        await pilot.press("tab")
        await type_text(pilot, "Parent")
        await pilot.press("enter")  # creates Pat Parent and opens them
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "child")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "zzzzqq")
        await pilot.press("enter")  # New person…
        await pilot.pause()
        await type_text(pilot, "Kim")
        await pilot.press("enter")  # creates Kim and opens them nested
        await pilot.pause()
        await pilot.press("escape")  # back to Pat, no diff
        await pilot.pause()
        return head(app), "\n".join(option_texts(app))

    header, rows = drive(tmp_path, script)
    assert "Pat Parent" in header and "Children" in rows and "Kim" in rows


def test_children_of_every_couple_come_under_one_heading_after_the_partners(tmp_path):
    # A person with a lone-parent group of children and a couple with a partner: the couple's children used to be
    # listed right below the partner, as if they belonged to the partnership.
    family = """\
dad:
  name: {given: Dad, surname: Ames}
mum:
  name: {given: Mum, surname: Ames}
dad + mum:
  events:
    - {type: marriage, date: 1900}
alone:
  name: {given: Alone, surname: Ames}
  parents: [dad]
joint:
  name: {given: Joint, surname: Ames}
  parents: [dad, mum]
"""
    folder(tmp_path, family=family)

    async def script(pilot, app):
        app.open_person("dad")
        await pilot.pause()
        return [t.strip() for t in option_texts(app)]

    rows = drive(tmp_path, script)
    assert rows.count("Children") == 1
    assert rows.index("Partners") < rows.index("Children")
    after = rows[rows.index("Children") + 1 :]
    assert after[:2] == ["Alone Ames", "Joint Ames"]
    between = rows[rows.index("Partners") + 1 : rows.index("Children")]
    assert not any("Ames" in r and "▸" not in r for r in between)
