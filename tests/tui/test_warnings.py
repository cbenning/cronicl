from conftest import FAMILY, drive, folder, highlight, option_texts, screen_name, texts

PROBLEMS = FAMILY + """
strange-sam:
  name: {given: Sam, surname: Strange}
  sex: M
  birth: 1950

blank-bea:
  name: {given: Bea, surname: Blank}
  sex:
  birth: 1960

alive-al:
  name: {given: Al, surname: Alive}
  birth: 1990
  death: 'no'

vague-vic:
  name: {given: Vic, surname: Vague}
  birth: 12 March 1900
"""


def head(app):
    from textual.widgets import Static

    return str(app.screen.query_one("#person-head", Static).content)


async def open_warnings(pilot, app):
    await pilot.press("f2")
    await pilot.pause()


def test_the_warnings_screen_groups_issues_by_person(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        return screen_name(app), "\n".join(option_texts(app, "#warnings"))

    name, shown = drive(tmp_path, script)
    assert name == "WarningsScreen"
    for who in ("Sam Strange", "Bea Blank", "Al Alive", "Vic Vague"):
        assert who in shown
    assert "W-BAD-SEX" in shown and "W-BLANK" in shown and "W-DATE-UNPARSED" in shown


def test_enter_jumps_to_the_person_with_the_cursor_on_the_offending_row(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        from textual.widgets import OptionList

        await open_warnings(pilot, app)
        await highlight(pilot, app, "W-BAD-SEX", selector="#warnings")
        await pilot.press("enter")
        await pilot.pause()
        widget = app.screen.query_one("#record", OptionList)
        return screen_name(app), head(app), str(widget.get_option_at_index(widget.highlighted).prompt)

    name, header, row = drive(tmp_path, script)
    assert name == "PersonScreen" and "Sam Strange" in header and "sex" in row


def test_f_on_a_blank_field_shows_a_diff_and_y_writes_it(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        await highlight(pilot, app, "W-BLANK", selector="#warnings")
        await pilot.press("f")
        await pilot.pause()
        shown = screen_name(app), texts(app)
        await pilot.press("y")
        await pilot.pause()
        return shown, screen_name(app), "\n".join(option_texts(app, "#warnings"))

    shown, after, remaining = drive(tmp_path, script)
    assert shown[0] == "DiffScreen" and "-  sex:" in shown[1]
    assert after == "WarningsScreen" and "W-BLANK" not in remaining
    assert "  sex:\n" not in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_a_possible_death_asks_and_the_default_keeps_the_person_alive(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        await highlight(pilot, app, "death date", selector="#warnings")
        await pilot.press("f")
        await pilot.pause()
        asked = screen_name(app), texts(app)
        await pilot.press("enter")  # the default
        await pilot.pause()
        diff = texts(app)
        await pilot.press("n")  # back: the fix is taken back out
        await pilot.pause()
        return asked, diff, app.session.changed

    asked, diff, changed = drive(tmp_path, script)
    assert asked[0] == "ChoiceEditor" and "they are alive" in asked[1] and "they died" in asked[1]
    assert "-  death: 'no'" in diff and not changed
    assert "death: 'no'" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_choosing_they_died_writes_unknown(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        await highlight(pilot, app, "death date", selector="#warnings")
        await pilot.press("f")
        await pilot.pause()
        await highlight(pilot, app, "they died", selector="#choices")
        await pilot.press("enter")
        await pilot.pause()
        diff = texts(app)
        await pilot.press("y")
        await pilot.pause()
        return diff

    diff = drive(tmp_path, script)
    assert "+  death: unknown" in diff
    assert "death: unknown" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_a_warning_without_a_fix_says_so(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        await highlight(pilot, app, "W-DATE-UNPARSED", selector="#warnings")
        # the first W-DATE-UNPARSED row is the death one; move to Vic's birth date
        from textual.widgets import OptionList

        widget = app.screen.query_one("#warnings", OptionList)
        for i in range(widget.option_count):
            if "12 March" in str(widget.get_option_at_index(i).prompt):
                widget.highlighted = i
        await pilot.press("f")
        await pilot.pause()
        return screen_name(app), app.session.changed

    name, changed = drive(tmp_path, script)
    assert name == "WarningsScreen" and not changed


def test_escape_goes_back_and_the_finder_offers_w_too(tmp_path):
    folder(tmp_path, family=PROBLEMS)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        return screen_name(app)

    assert drive(tmp_path, script) == "FinderScreen"


def test_a_clean_family_says_there_is_nothing_to_fix(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_warnings(pilot, app)
        return texts(app)

    assert "No warnings" in drive(tmp_path, script)
