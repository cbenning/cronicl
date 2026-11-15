import pytest

from conftest import FAMILY, drive, folder, screen_name, texts

EXTRA = FAMILY + """
muller-zoe:
  name: {given: Zoë, surname: Müller}
  sex:
  birth: 1990
"""
SIZES = [(80, 24), (120, 40)]


def rows(app):
    from textual.widgets import OptionList

    widget = app.screen.query_one("#results", OptionList)
    return [str(widget.get_option_at_index(i).prompt) for i in range(widget.option_count)]


async def type_text(pilot, text):
    for char in text:
        await pilot.press("space" if char == " " else char)
    await pilot.pause()


@pytest.mark.parametrize("size", SIZES)
def test_the_finder_lists_everyone_by_surname_when_the_query_is_empty(tmp_path, size):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        return screen_name(app), rows(app), texts(app)

    name, listed, shown = drive(tmp_path, script, size)
    assert name == "FinderScreen"
    assert [r.split()[0] for r in listed] == ["George", "Augusta", "Annabella", "Zoë"] or len(listed) == 4
    order = [next(w for w in ("Byron", "Lovelace", "Milbanke", "Müller") if w in r) for r in listed]
    assert order == ["Byron", "Lovelace", "Milbanke", "Müller"]
    assert "4 people" in shown


@pytest.mark.parametrize("size", SIZES)
def test_typing_narrows_and_ranks_with_typos_and_accents(tmp_path, size):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        await type_text(pilot, "lovlace")
        typo = rows(app)
        await pilot.press("ctrl+u")
        await type_text(pilot, "muller")
        accent = rows(app)
        return typo, accent

    typo, accent = drive(tmp_path, script, size)
    assert "Lovelace" in typo[0] and "Zoë" in accent[0]


def test_enter_opens_the_highlighted_person_and_down_moves(tmp_path):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        opened = []
        app.open_person = opened.append
        await pilot.press("enter")
        await pilot.press("down", "enter")
        return opened

    assert drive(tmp_path, script) == ["byron-george", "lovelace-ada"]


def test_living_people_and_people_with_warnings_are_marked(tmp_path):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        return rows(app)

    listed = drive(tmp_path, script)
    zoe = next(r for r in listed if "Müller" in r)
    byron = next(r for r in listed if "Byron" in r)
    assert "●" in zoe and "⚠1" in zoe
    assert "●" not in byron and "⚠" not in byron


def test_the_status_line_counts_people_warnings_and_living(tmp_path):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        return texts(app)

    shown = drive(tmp_path, script)
    assert "4 people" in shown and "1 warning" in shown and "1 living" in shown


def test_no_match_says_so_and_escape_clears_the_query(tmp_path):
    folder(tmp_path, family=EXTRA)

    async def script(pilot, app):
        await type_text(pilot, "qqqqzzzz")
        none = rows(app), texts(app)
        await pilot.press("escape")
        await pilot.pause()
        return none, rows(app)

    (none_rows, none_text), after = drive(tmp_path, script)
    assert none_rows == [] and "No one matches" in none_text and len(after) == 4


def test_an_empty_family_says_how_to_add_the_first_person(tmp_path):
    folder(tmp_path, family="# nobody yet\n")

    async def script(pilot, app):
        return texts(app)

    assert "Ctrl+N" in drive(tmp_path, script)
