import contextlib
import subprocess

from conftest import SITE, drive, folder, screen_name, texts


def test_an_empty_folder_shows_the_start_screen(tmp_path):
    async def script(pilot, app):
        return screen_name(app), texts(app)

    name, shown = drive(tmp_path, script)
    assert name == "StartScreen" and "Start a new family here" in shown and "Import a GEDCOM file" in shown


def test_starting_a_family_writes_the_files_and_opens_the_finder(tmp_path):
    async def script(pilot, app):
        await pilot.press("enter")  # the first option
        await pilot.pause()
        return screen_name(app)

    assert drive(tmp_path, script) == "FinderScreen"
    assert (tmp_path / "family.yml").is_file() and (tmp_path / "site.yml").is_file()


def test_importing_a_gedcom_file_asks_then_writes(tmp_path, sample_ged):
    async def script(pilot, app):
        await pilot.press("down", "enter")  # Import
        await pilot.pause()
        for char in str(sample_ged):
            await pilot.press(char if char != "/" else "slash")
        await pilot.press("enter")
        await pilot.pause()
        asked = texts(app)
        await pilot.press("y")
        await pilot.pause()
        return asked, screen_name(app)

    asked, name = drive(tmp_path, script)
    assert "people" in asked and name == "FinderScreen"
    assert "smith-bob" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_an_unreadable_family_lists_the_error_with_its_line(tmp_path):
    folder(tmp_path, family="a:\n  name: [unclosed\n")

    async def script(pilot, app):
        return screen_name(app), texts(app)

    name, shown = drive(tmp_path, script)
    assert name == "ProblemScreen" and "family.yml:" in shown and "e opens the file" in shown


def test_e_opens_the_editor_at_the_error_line_then_reloads(tmp_path, monkeypatch):
    folder(tmp_path, family="a:\n  name: [unclosed\n")
    calls = []

    def fake_editor(command, **kwargs):
        calls.append(command)
        (tmp_path / "family.yml").write_text("a:\n  name: {given: A}\n", encoding="utf-8")  # the owner fixes it
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cronicl.tui.screens.problem.subprocess.run", fake_editor)
    monkeypatch.setenv("EDITOR", "myeditor")
    monkeypatch.setattr("cronicl.tui.app.CroniclApp.suspend", lambda self: contextlib.nullcontext())  # no real terminal in a test

    async def script(pilot, app):
        await pilot.press("e")
        await pilot.pause()
        return screen_name(app)

    assert drive(tmp_path, script) == "FinderScreen"
    assert calls and calls[0][0] == "myeditor" and calls[0][1].startswith("+") and calls[0][2].endswith("family.yml")


def test_the_old_layout_offers_migration(tmp_path, legacy_folder):
    async def script(pilot, app):
        shown = texts(app)
        await pilot.press("m")
        await pilot.pause()
        return screen_name(app), shown

    name, shown = drive(legacy_folder, script)
    assert "m converts" in shown and name == "FinderScreen"
    assert (legacy_folder / "family.yml").is_file()
