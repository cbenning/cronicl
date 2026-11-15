"""Every screen renders without an error at a small and a large terminal."""
import pytest

from conftest import FAMILY, drive, folder, screen_name, texts

SIZES = [(80, 24), (120, 40)]
PROBLEMS = FAMILY + "\nstrange-sam:\n  name: {given: Sam, surname: Strange}\n  sex: M\n  birth: 1950\n"


def render(app):
    assert app.export_screenshot()  # raises if a widget fails to render


@pytest.mark.parametrize("size", SIZES)
def test_every_screen_renders(tmp_path, size):
    folder(tmp_path, family=PROBLEMS)
    seen = []

    async def script(pilot, app):
        async def visit(label):
            await pilot.pause()
            render(app)
            seen.append((label, screen_name(app)))

        await visit("finder")
        await pilot.press("f1"); await visit("help"); await pilot.press("escape")
        await pilot.press("f2"); await visit("warnings"); await pilot.press("escape")
        app.open_person("byron-george"); await pilot.pause()
        await visit("person")
        from conftest import highlight

        await highlight(pilot, app, "Annabella Milbanke"); await pilot.press("enter"); await visit("person with a couple expanded")
        await pilot.press("a"); await visit("palette"); await pilot.press("escape")
        await pilot.press("ctrl+e"); await visit("raw"); await pilot.press("escape")
        await highlight(pilot, app, "given: George"); await pilot.press("enter"); await visit("text editor"); await pilot.press("escape")
        await highlight(pilot, app, "date: 1788-01-22"); await pilot.press("enter"); await visit("date editor"); await pilot.press("escape")
        await highlight(pilot, app, "sex: male"); await pilot.press("enter"); await visit("choice editor"); await pilot.press("escape")
        await highlight(pilot, app, "place: London"); await pilot.press("enter"); await visit("place editor"); await pilot.press("escape")
        await pilot.press("escape"); await pilot.pause()
        app.open_person("lovelace-ada"); await pilot.pause()
        await highlight(pilot, app, "- byron-george"); await pilot.press("enter"); await visit("people picker"); await pilot.press("escape")
        await pilot.press("a"); await pilot.press("p", "a", "r", "t", "n", "e", "r", "enter"); await visit("partner picker"); await pilot.press("escape")
        from cronicl.core.recordedit import set_value

        app.session.stage("family.yml", set_value(app.session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
        await pilot.press("escape"); await visit("diff")
        await pilot.press("n")
        await pilot.press("escape", "y"); await pilot.pause()
        await pilot.press("ctrl+n"); await visit("new person")
        return seen

    result = drive(tmp_path, script, size)
    names = [n for _, n in result]
    for expected in ("FinderScreen", "HelpScreen", "WarningsScreen", "PersonScreen", "PaletteScreen", "RawScreen", "TextEditor", "DateEditor", "ChoiceEditor", "PeoplePicker", "DiffScreen", "NewPersonScreen"):
        assert expected in names, (expected, names)


def test_the_start_and_problem_screens_render(tmp_path):
    async def start(pilot, app):
        render(app)
        return screen_name(app)

    assert drive(tmp_path, start, (80, 24)) == "StartScreen"
    other = tmp_path / "broken"
    other.mkdir()
    folder(other, family="a:\n  name: [unclosed\n")

    async def problem(pilot, app):
        render(app)
        return screen_name(app)

    assert drive(other, problem, (80, 24)) == "ProblemScreen"
