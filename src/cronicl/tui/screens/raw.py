"""The raw pane: one record's YAML as text, for anything the field editors do not cover."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea

from ...core.recordedit import EditRefused, record_text, replace_record


class RawScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save")]

    def __init__(self, session, key: str, source: str) -> None:
        super().__init__()
        self.session, self.key, self.source = session, key, source

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide tall"):
            yield Label(f"{self.key}  ·  {self.source}", classes="dialog-title")
            yield TextArea(record_text(self.session.staged[self.source], self.key), id="area", language="yaml")
            yield Label("", id="raw-error")
            yield Label("Ctrl+S saves (the record is checked first) · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#area", TextArea).focus()

    def action_save(self) -> None:
        text = self.query_one("#area", TextArea).text
        try:
            new = replace_record(self.session.staged[self.source], self.key, text)
        except EditRefused as exc:
            self.query_one("#raw-error", Label).update(f"[b red]Cannot save:[/] {exc}")
            return
        if new != self.session.staged[self.source]:
            self.session.stage(self.source, new)
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
