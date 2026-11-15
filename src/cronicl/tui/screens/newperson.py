"""A new person: a given name, a surname and an id (proposed, editable)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

from ...core.slug import is_valid_id, person_slug, unique_id


class NewPersonScreen(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, taken: set[str], title: str = "New person") -> None:
        super().__init__()
        self.taken, self.heading = taken, title
        self.id_edited = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(placeholder="given names", id="given")
            yield Input(placeholder="surname", id="surname")
            yield Input(placeholder="id", id="new-id")
            yield Label("", id="new-error")
            yield Label("Tab moves · Enter creates · leave the names empty for an unknown person · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#given", Input).focus()
        self._propose()

    def _propose(self) -> None:
        given = self.query_one("#given", Input).value.strip()
        surname = self.query_one("#surname", Input).value.strip()
        base = person_slug(given, surname) if (given or surname) else "unknown"
        self.query_one("#new-id", Input).value = unique_id(base, self.taken)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("given", "surname") and not self.id_edited:
            self._propose()
        elif event.input.id == "new-id" and event.input.has_focus:
            self.id_edited = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        new_id = self.query_one("#new-id", Input).value.strip()
        error = self.query_one("#new-error", Label)
        if not is_valid_id(new_id):
            error.update("[b red]The id uses lower-case letters, digits and single hyphens[/]")
            return
        if new_id in self.taken:
            error.update(f"[b red]{new_id} is already someone else[/]")
            return
        self.dismiss(
            {
                "id": new_id,
                "given": self.query_one("#given", Input).value.strip(),
                "surname": self.query_one("#surname", Input).value.strip(),
            }
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
