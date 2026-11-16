"""The review step: exactly what would change in the files, and a choice to write it, go back, or throw it away."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Label, Static

from ..session import DiskChanged, Session, Unreadable


def diff_text(session: Session) -> Text:
    text = Text()
    for file_diff in session.diff():
        text.append(f"{file_diff.name}\n", style="bold underline")
        for line in file_diff.text.splitlines():
            style = "green" if line.startswith("+") and not line.startswith("+++") else "red" if line.startswith("-") and not line.startswith("---") else "cyan" if line.startswith("@@") else "dim" if line.startswith(("---", "+++")) else ""
            text.append(line + "\n", style=style)
        text.append("\n")
    return text


class DiffScreen(Screen[str]):
    BINDINGS = [
        Binding("enter,y", "write", "Write these changes"),
        Binding("n,escape", "back", "Keep editing"),
        Binding("x", "discard", "Discard all"),
        Binding("r", "reload", "Reload from disk", show=False),
    ]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.stale = False

    def compose(self) -> ComposeResult:
        yield Label("Review changes", id="diff-title")
        with VerticalScroll(id="diff-scroll"):
            yield Static(diff_text(self.session), id="diff-text")
        yield Label("", id="diff-message")
        yield Footer()

    def action_write(self) -> None:
        if self.stale:
            return
        try:
            self.session.commit()
        except DiskChanged as exc:
            self.stale = True
            self.query_one("#diff-message", Label).update(
                f"[b red]{', '.join(exc.names)} changed on disk since it was loaded.[/] Nothing was written. r reloads from disk (dropping your changes); Esc keeps editing."
            )
            return
        except Unreadable as exc:
            self.query_one("#diff-message", Label).update(f"[b red]{exc}[/] Nothing was written. Esc keeps editing.")
            return
        except (OSError, UnicodeDecodeError) as exc:
            self.query_one("#diff-message", Label).update(f"[b red]Could not write: {exc}.[/] Your changes are still staged. Esc keeps editing.")
            return
        self.dismiss("written")

    def action_back(self) -> None:
        self.dismiss("back")

    def action_discard(self) -> None:
        self.session.discard()
        self.dismiss("discarded")

    def action_reload(self) -> None:
        if self.stale:
            try:
                self.session.reload()
            except (OSError, UnicodeDecodeError) as exc:
                self.query_one("#diff-message", Label).update(f"[b red]Could not reload: {exc}.[/]")
                return
            self.dismiss("reloaded")
