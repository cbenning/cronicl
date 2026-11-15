"""Helpers for driving the TUI headless with Textual's Pilot, without a pytest plugin."""
import asyncio

import pytest

from cronicl.tui.app import CroniclApp

SITE = "title: T\nschema_version: 3\n"
FAMILY = """\
byron-george:
  name: {given: George, surname: Byron}
  sex: male
  birth: {date: 1788-01-22, place: "London, England"}
  death: {date: 1824-04-19, place: "Missolonghi, Greece"}

milbanke-annabella:
  name: {given: Annabella, surname: Milbanke}
  sex: female
  birth: 1792-05-17

byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02, place: "Seaham, England"}

lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace}
  sex: female
  birth: {date: 1815-12-10, place: "London, England"}
  death: 1852-11-27
  parents: [byron-george, milbanke-annabella]
"""


def folder(tmp_path, family=FAMILY, site=SITE, extra=None):
    if site is not None:
        (tmp_path / "site.yml").write_text(site, encoding="utf-8")
    if family is not None:
        (tmp_path / "family.yml").write_text(family, encoding="utf-8")
    for name, text in (extra or {}).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def drive(path, script, size=(80, 24)):
    """Run `script(pilot, app)` against the app on `path`; return what it returns."""

    async def go():
        app = CroniclApp(path)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            return await script(pilot, app)

    return asyncio.run(go())


@pytest.fixture
def make(tmp_path):
    def build(**kwargs):
        return folder(tmp_path, **kwargs)

    return build


def screen_name(app):
    return type(app.screen).__name__


def texts(app):
    """All the visible text of the current screen, joined (Static, Label and OptionList rows)."""
    from textual.widgets import Label, OptionList, Static

    parts = []
    for widget in app.screen.query("*"):
        if isinstance(widget, OptionList):
            parts += [str(widget.get_option_at_index(i).prompt) for i in range(widget.option_count)]
        elif isinstance(widget, (Static, Label)):
            parts.append(str(widget.content))
    return "\n".join(parts)


@pytest.fixture
def legacy_folder(tmp_path):
    import shutil
    from pathlib import Path

    target = tmp_path / "old"
    shutil.copytree(Path(__file__).resolve().parents[1] / "fixtures" / "legacy", target)
    return target
