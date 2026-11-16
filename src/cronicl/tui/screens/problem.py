"""The screen for a family that cannot be loaded: show each error with its file and line, open it in an editor."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Label, OptionList
from textual.widgets.option_list import Option

from .. import bridge


def editor_command() -> str:
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


class ProblemScreen(Screen):
    BINDINGS = [
        Binding("e", "edit", "Open in editor"),
        Binding("r", "reload", "Reload"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, issues) -> None:
        super().__init__()
        self.issues = [i for i in issues if i.severity == "error"] or list(issues)

    def compose(self) -> ComposeResult:
        yield Label("This family cannot be loaded yet", id="problem-title")
        rows = [Option(f"{i.path or ''}{':' + str(i.line) if i.line else ''}  {i.message}", id=str(n)) for n, i in enumerate(self.issues)]
        yield OptionList(*rows, id="problems")
        yield Label("e opens the file at the error, r reloads", classes="hint")
        yield Footer()

    def _selected(self):
        widget = self.query_one("#problems", OptionList)
        index = widget.highlighted if widget.highlighted is not None else 0
        return self.issues[index] if self.issues else None

    def action_edit(self) -> None:
        issue = self._selected()
        if issue is None or not issue.path:
            return
        path = Path(self.app.data_dir) / issue.path
        with self.app.suspend():
            subprocess.run([*shlex.split(editor_command()), f"+{issue.line or 1}", str(path)])
        self.app.open_home()

    def action_reload(self) -> None:
        self.app.open_home()
