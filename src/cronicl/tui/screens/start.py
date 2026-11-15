"""The screen for an empty folder: start a family here, or import a GEDCOM file."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Label, OptionList
from textual.widgets.option_list import Option

from .. import bridge
from .modals import Confirm, Message, Prompt


class StartScreen(Screen):
    BINDINGS = [("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Label("cronicl", id="start-title")
        yield Label(f"There is no family file in {self.app.data_dir}", id="start-sub")
        yield OptionList(
            Option("Start a new family here", id="init"),
            Option("Import a GEDCOM file…", id="import"),
            Option("Quit", id="quit"),
            id="start-options",
        )
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        choice = event.option.id
        if choice == "quit":
            self.app.exit()
        elif choice == "init":
            from ...cli import cmd_init

            code, text = bridge.call(cmd_init, dir=str(self.app.data_dir))
            if code != 0:
                self.app.push_screen(Message(text, "Could not start a family"))
            else:
                self.app.open_home()
        elif choice == "import":
            self.app.push_screen(Prompt("Path of the GEDCOM file", placeholder="~/Downloads/family.ged"), self._have_path)

    def _have_path(self, path: str | None) -> None:
        if not path:
            return
        from ...cli import cmd_import

        source = Path(path).expanduser()
        code, text = bridge.call(cmd_import, file=str(source), dir=str(self.app.data_dir), apply=False)
        if code != 0 or not source.is_file():
            self.app.push_screen(Message(text or f"cannot read {source}", "Could not read that file"))
            return
        summary = text.replace("dry run; re-run with --apply (-a) to write files", "").strip()

        def decided(yes: bool | None) -> None:
            if yes:
                code2, text2 = bridge.call(cmd_import, file=str(source), dir=str(self.app.data_dir), apply=True)
                if code2 != 0:
                    self.app.push_screen(Message(text2, "Import failed"))
                    return
                self.app.open_home()

        self.app.push_screen(Confirm(summary, "Import", "Import this file?"), decided)
