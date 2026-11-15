"""Editors for one field, chosen by the field's kind: plain text, long text, dates, choices, places, people."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from ...core.catalog import COUPLE_EVENT_TYPES, EVENT_TYPES, FIELDS, Field
from ...core.dates import format_date, is_unknown, parse_date, parse_span
from ...core.search import tokenize


def catalog_key(path: tuple) -> str | None:
    """The catalog entry for a path in a record: ('a','events',1,'type') is 'events[].type'; a bare birth is 'birth.date'."""
    steps = path[1:]
    out = ""
    for step in steps:
        out += "[]" if isinstance(step, int) else (("." if out else "") + step)
    if out in ("birth", "death"):
        out += ".date"
    if out.endswith("[]") and out[:-2] in FIELDS:
        out = out[:-2]  # an item of parents, name.also, cite: the list's own entry
    return out if out in FIELDS else None


def title_of(path: tuple) -> str:
    return " · ".join(str(step) for step in path[1:] if isinstance(step, str))


class _Base(ModalScreen):
    CSS_CLASSES = "editor"

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self.heading, self.value = title, value

    def action_cancel(self) -> None:
        self.dismiss(None)


class TextEditor(_Base):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(value=self.value, id="value")
            yield Label("Enter saves · empty removes the field · Esc cancels", classes="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class LongTextEditor(_Base):
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.heading, classes="dialog-title")
            yield TextArea(self.value, id="area")
            yield Label("Ctrl+S saves · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#area", TextArea).focus()

    def action_save(self) -> None:
        self.dismiss(self.query_one("#area", TextArea).text.strip("\n"))


_TEMPLATES = {"f2": ("ABT ", None), "f3": ("BEF ", None), "f4": ("AFT ", None), "f5": ("BET  AND ", 4), "f6": ("FROM  TO ", 5), "f7": ("unknown", None)}


class DateEditor(_Base):
    BINDINGS = [Binding("escape", "cancel", "Cancel")] + [Binding(k, f"template('{k}')", show=False) for k in _TEMPLATES]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(value=self.value, id="value")
            yield Label("", id="reading")
            yield Label("F2 about · F3 before · F4 after · F5 between · F6 from-to · F7 unknown · Enter saves", classes="hint")

    def on_mount(self) -> None:
        self._read(self.value)

    def _read(self, text: str) -> None:
        text = text.strip()
        reading = self.query_one("#reading", Label)
        if not text:
            reading.update("[dim]empty: the field is removed[/dim]")
        elif parse_date(text) is not None or parse_span(text) is not None or is_unknown(text):
            reading.update(f"[green]{format_date(text)}[/green]")
        else:
            reading.update("[red]not a date I can read[/red] [dim](it is still saved, as text)[/dim]")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._read(event.value)

    def action_template(self, key: str) -> None:
        text, cursor = _TEMPLATES[key]
        box = self.query_one("#value", Input)
        box.value = text
        box.cursor_position = len(text) if cursor is None else cursor

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class ChoiceEditor(_Base):
    """A list of options. With `free` the owner may also type their own value (shown first as Use "…")."""

    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("down", "move(1)", show=False), Binding("up", "move(-1)", show=False)]

    def __init__(self, title: str, options: list[tuple[str, str]], value: str = "", free: bool = False) -> None:
        super().__init__(title, value)
        self.options, self.free = options, free  # [(value, description)]
        self._values: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall"):
            yield Label(self.heading, classes="dialog-title")
            if self.free:
                yield Input(value="", placeholder="type to search, or type a value of your own", id="typed")
            yield OptionList(id="choices")
            yield Label("Enter picks · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self._fill("")
        (self.query_one("#typed", Input) if self.free else self.query_one("#choices", OptionList)).focus()

    def _fill(self, typed: str) -> None:
        words = tokenize(typed)
        choices = self.query_one("#choices", OptionList)
        choices.clear_options()
        self._values = []
        rows: list[Option] = []
        if self.free and typed.strip():
            self._values.append(typed.strip())
            rows.append(Option(f'Use "{typed.strip()}"', id="use"))
        matches = 0
        for value, note in self.options:
            hay = " ".join(tokenize(f"{value} {note}"))
            if all(w in hay for w in words):
                self._values.append(value)
                label = value if not note else f"{value}  [dim]{note}[/dim]"
                rows.append(Option(label, id=f"v{len(self._values) - 1}"))
                matches += 1
        choices.add_options(rows)
        if rows:
            choices.highlighted = 1 if (self.free and typed.strip() and matches) else 0
        elif not typed.strip():
            choices.highlighted = None
        if not typed.strip() and self.value in [v for v, _ in self.options]:
            for i, v in enumerate(self._values):
                if v == self.value:
                    choices.highlighted = i

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "typed":
            self._fill(event.value)

    def _pick(self) -> None:
        choices = self.query_one("#choices", OptionList)
        if choices.highlighted is not None and choices.option_count:
            self.dismiss(self._values[choices.highlighted])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._pick()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._pick()

    def action_move(self, step: int) -> None:
        choices = self.query_one("#choices", OptionList)
        if choices.option_count:
            current = choices.highlighted if choices.highlighted is not None else -1
            choices.highlighted = max(0, min(choices.option_count - 1, current + step))


class PeoplePicker(_Base):
    """Pick a person (by name), or "New person…". Returns the id, or NEW."""

    NEW = "__new__"
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("down", "move(1)", show=False), Binding("up", "move(-1)", show=False)]

    def __init__(self, title: str, family, exclude: set[str], allow_new: bool = True, current: str = "") -> None:
        super().__init__(title, current)
        self.family, self.exclude, self.allow_new = family, exclude, allow_new

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog tall"):
            yield Label(self.heading, classes="dialog-title")
            yield Input(placeholder="Find a person…", id="people-query")
            yield OptionList(id="people")
            yield Label("Enter picks · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#people-query", Input).focus()
        self._fill("")

    def _fill(self, query: str) -> None:
        from .finder import row_text

        people = self.query_one("#people", OptionList)
        people.clear_options()
        rows = [r for r in self.family.rows(query, limit=200) if r.id not in self.exclude]
        options = [Option(row_text(r), id=r.id) for r in rows]
        if self.allow_new:
            options.append(Option("＋ New person…", id=self.NEW))
        people.add_options(options)
        people.highlighted = 0 if options else None

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    def _pick(self) -> None:
        people = self.query_one("#people", OptionList)
        if people.highlighted is not None and people.option_count:
            self.dismiss(people.get_option_at_index(people.highlighted).id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._pick()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._pick()

    def action_move(self, step: int) -> None:
        people = self.query_one("#people", OptionList)
        if people.option_count:
            current = people.highlighted if people.highlighted is not None else -1
            people.highlighted = max(0, min(people.option_count - 1, current + step))


def descendants(family, pid: str) -> set[str]:
    """Everyone below `pid` through the children of their couples."""
    seen: set[str] = set()
    stack = [pid]
    relations = family.relations
    while stack:
        current = stack.pop()
        for cid in relations.couples_of.get(current, []):
            for kid in relations.kids.get(cid, []):
                if kid not in seen:
                    seen.add(kid)
                    stack.append(kid)
    return seen


def editor_for(app, record_key: str, path: tuple, value: str):
    """The editor screen for the field at `path`, or None when the row is not a field the editors know."""
    key = catalog_key(path)
    if key is None:
        return None
    field: Field = FIELDS[key]
    title = title_of(path) or key
    family = app.family
    kind = field.kind
    couple = "+" in record_key
    if key == "events[].type":
        types = COUPLE_EVENT_TYPES if couple else EVENT_TYPES
        return ChoiceEditor(title, [(slug, note) for slug, note in types.items()], value, free=True)
    if kind == "choice":
        return ChoiceEditor(title, [(c, "") for c in field.choices or ()], value)
    if kind == "flag":
        return ChoiceEditor(title, [("true", field.description)], value)
    if kind == "date":
        return DateEditor(title, value)
    if kind == "longtext":
        return LongTextEditor(title, value)
    if kind == "place":
        return ChoiceEditor(title, [(p, "") for p in family.places()], value, free=True)
    if kind == "file":
        return ChoiceEditor(title, [(f, "") for f in family.media_files()], value, free=True)
    if kind == "people":
        own = record_key
        others = {p for p in family.tree.people[own].parents if p != value} if own in family.tree.people else set()
        exclude = {own} | others | descendants(family, own)
        return PeoplePicker(title, family, exclude, True, value)
    return TextEditor(title, value)
