"""The finder: type to narrow the list of people, Enter to open one."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, OptionList
from textual.widgets.option_list import Option


def row_text(row) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append("● " if row.living else "  ", style="bold yellow")
    text.append(f"{row.name:<26.26} ", style="bold")
    text.append(f"{row.years:<12.12} ", style="dim")
    text.append(f"{row.place:<20.20} ", style="dim")
    text.append(f"{row.id}", style="dim italic")
    if row.warnings:
        text.append(f"  ⚠{row.warnings}", style="bold red")
    return text


class FinderScreen(Screen):
    BINDINGS = [
        Binding("down", "move(1)", "Next", show=False),
        Binding("up", "move(-1)", "Previous", show=False),
        Binding("pagedown", "move(8)", "Page down", show=False),
        Binding("pageup", "move(-8)", "Page up", show=False),
        Binding("escape", "clear", "Clear"),
        Binding("ctrl+n", "new_person", "New person"),
        Binding("ctrl+w", "warnings", "Warnings"),
        Binding("f1", "help", "Help"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="finder"):
            yield Input(placeholder="Find a person: name, year, place…", id="query")
            yield Label("", id="status")
            yield OptionList(id="results")
            yield Label("", id="finder-empty", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#query", Input).focus()
        self.refresh_rows()

    # ---- content --------------------------------------------------------------------------------------------------
    def refresh_rows(self) -> None:
        family = self.app.family
        query = self.query_one("#query", Input).value
        rows = family.rows(query)
        results = self.query_one("#results", OptionList)
        results.clear_options()
        results.add_options([Option(row_text(r), id=r.id) for r in rows])
        if rows:
            results.highlighted = 0
        people = len(family.tree.people)
        warnings = sum(1 for i in family.issues if i.severity != "info")
        living = family.living_count()
        self.query_one("#status", Label).update(
            f"{people} {'person' if people == 1 else 'people'} · {warnings} {'warning' if warnings == 1 else 'warnings'} · {living} living"
        )
        empty = self.query_one("#finder-empty", Label)
        if not people:
            empty.update("No people yet. Ctrl+N adds the first one.")
        elif not rows:
            empty.update("No one matches. Esc clears the search.")
        else:
            empty.update("")

    def on_input_changed(self, event: Input.Changed) -> None:
        self.refresh_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.app.open_person(event.option.id)

    # ---- actions --------------------------------------------------------------------------------------------------
    def _open_highlighted(self) -> None:
        results = self.query_one("#results", OptionList)
        if results.highlighted is not None and results.option_count:
            option = results.get_option_at_index(results.highlighted)
            if option.id:
                self.app.open_person(option.id)

    def action_move(self, step: int) -> None:
        results = self.query_one("#results", OptionList)
        if not results.option_count:
            return
        current = results.highlighted if results.highlighted is not None else -1
        results.highlighted = max(0, min(results.option_count - 1, current + step))

    def action_clear(self) -> None:
        query = self.query_one("#query", Input)
        if query.value:
            query.value = ""

    def action_new_person(self) -> None:
        self.app.new_person()

    def action_warnings(self) -> None:
        self.app.open_warnings()

    def action_help(self) -> None:
        self.app.open_help()
