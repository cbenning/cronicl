from conftest import FAMILY, drive, folder, screen_name, texts
from cronicl.core.recordedit import set_value


def stage_change(app):
    app.session.stage("family.yml", set_value(app.session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))


def test_with_nothing_staged_review_just_continues(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        results = []
        app.review_changes(results.append)
        await pilot.pause()
        return results, screen_name(app)

    results, name = drive(tmp_path, script)
    assert results == ["nothing"] and name == "FinderScreen"


def test_the_diff_screen_shows_the_changed_lines_and_y_writes(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        results = []
        stage_change(app)
        app.review_changes(results.append)
        await pilot.pause()
        shown = texts(app)
        name = screen_name(app)
        await pilot.press("y")
        await pilot.pause()
        return shown, name, results, screen_name(app)

    shown, name, results, after = drive(tmp_path, script)
    assert name == "DiffScreen" and "-  sex: female" in shown and "+  sex: other" in shown and "family.yml" in shown
    assert results == ["written"] and after == "FinderScreen"
    assert "sex: other" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_n_and_escape_go_back_without_writing(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        results = []
        stage_change(app)
        app.review_changes(results.append)
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        app.review_changes(results.append)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        return results, app.session.changed

    results, changed = drive(tmp_path, script)
    assert results == ["back", "back"] and changed
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_x_discards_everything(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        results = []
        stage_change(app)
        app.review_changes(results.append)
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        return results, app.session.changed

    results, changed = drive(tmp_path, script)
    assert results == ["discarded"] and not changed
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_a_file_changed_on_disk_is_refused_with_a_message_and_r_reloads(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        results = []
        stage_change(app)
        (tmp_path / "family.yml").write_text(FAMILY + "\n# elsewhere\n", encoding="utf-8")
        app.review_changes(results.append)
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        message = texts(app)
        disk_before = (tmp_path / "family.yml").read_text(encoding="utf-8")
        await pilot.press("r")
        await pilot.pause()
        return message, disk_before, results, app.session.changed

    message, disk, results, changed = drive(tmp_path, script)
    assert "changed on disk" in message and disk.endswith("# elsewhere\n")
    assert results == ["reloaded"] and not changed


def test_a_write_failure_shows_a_message_and_keeps_the_staged_change(tmp_path, monkeypatch):
    folder(tmp_path)

    async def script(pilot, app):
        stage_change(app)
        monkeypatch.setattr("cronicl.tui.session.os.replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError("read-only")))
        app.review_changes(lambda r: None)
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return screen_name(app), texts(app), app.session.changed

    name, shown, changed = drive(tmp_path, script)
    assert name == "DiffScreen" and "Could not write" in shown and changed
