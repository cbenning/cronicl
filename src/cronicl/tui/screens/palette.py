"""The field palette: search the fields a record can still take, and add one."""
from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from ...core.catalog import COUPLE_EVENT_TYPES, EVENT_TYPES, Field, fields_for
from ...core.search import _match, tokenize

VALUE_EVENT_TYPES = ("occupation", "education", "religion", "nationality")


@dataclass
class Entry:
    label: str
    note: str
    action: tuple  # ("field", Field) | ("event", slug) | ("partner",) | ("child",) | ("custom",)


def build_entries(kind: str, present: set[tuple], parent_count: int) -> list[Entry]:
    """What can be added to a `person` or `couple` record that has the fields `present` (path steps below the key)."""
    out: list[Entry] = []
    for field in fields_for(kind):
        steps = tuple(field.path.split("."))
        if field.path == "events":
            continue  # replaced by one entry per event type
        if field.path == "parents":
            if parent_count >= 2:
                continue
        elif field.once and steps in present:
            continue
        out.append(Entry(field.path, field.description, ("field", field)))
    for slug, note in (COUPLE_EVENT_TYPES if kind == "couple" else EVENT_TYPES).items():
        out.append(Entry(f"event: {slug}", note, ("event", slug)))
    if kind == "person":
        out.append(Entry("partner", "add a partner and their marriage", ("partner",)))
        out.append(Entry("child", "add a child", ("child",)))
    out.append(Entry("your own key (x-…)", "a field of your own; it is kept and never reported", ("custom",)))
    return out


def matches(entry: Entry, words: list[str]) -> bool:
    if not words:
        return True
    tokens = tokenize(f"{entry.label} {entry.note}")
    return all(any(_match(w, t) > 0 for t in tokens) for w in words)


class PaletteScreen(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("down", "move(1)", show=False), Binding("up", "move(-1)", show=False)]

    def __init__(self, title: str, entries: list[Entry]) -> None:
        super().__init__()
        self.heading, self.entries = title, entries
        self.shown: list[Entry] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(placeholder="Search fields: nick, resid, parent…", id="query")
            yield OptionList(id="fields")
            yield Label("Enter adds · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#query", Input).focus()
        self._fill("")

    def _fill(self, query: str) -> None:
        words = tokenize(query)
        self.shown = [e for e in self.entries if matches(e, words)]
        fields = self.query_one("#fields", OptionList)
        fields.clear_options()
        rows = []
        for i, entry in enumerate(self.shown):
            text = Text(no_wrap=True, overflow="ellipsis")
            text.append(f"{entry.label:<22}", style="bold")
            text.append(entry.note, style="dim")
            rows.append(Option(text, id=str(i)))
        fields.add_options(rows)
        fields.highlighted = 0 if rows else None

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    def _pick(self) -> None:
        fields = self.query_one("#fields", OptionList)
        if fields.highlighted is not None and self.shown:
            self.dismiss(self.shown[fields.highlighted].action)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._pick()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._pick()

    def action_move(self, step: int) -> None:
        fields = self.query_one("#fields", OptionList)
        if fields.option_count:
            current = fields.highlighted if fields.highlighted is not None else -1
            fields.highlighted = max(0, min(fields.option_count - 1, current + step))

    def action_cancel(self) -> None:
        self.dismiss(None)
