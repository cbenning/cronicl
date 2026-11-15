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
