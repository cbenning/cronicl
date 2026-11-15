"""Small dialogs: a message, a yes/no question, a one-line prompt."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class Message(ModalScreen[None]):
    BINDINGS = [Binding("escape,enter", "close", "Close")]

    def __init__(self, text: str, title: str = "") -> None:
        super().__init__()
        self.text, self.heading = text, title

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            if self.heading:
                yield Label(self.heading, classes="dialog-title")
            yield Static(self.text, id="message-text")
            yield Label("Enter closes", classes="hint")

    def action_close(self) -> None:
        self.dismiss(None)


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("y,enter", "yes", "Yes"), Binding("n,escape", "no", "No")]

    def __init__(self, text: str, yes: str = "Yes", title: str = "") -> None:
        super().__init__()
        self.text, self.yes_label, self.heading = text, yes, title

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            if self.heading:
                yield Label(self.heading, classes="dialog-title")
            yield Static(self.text, id="confirm-text")
            yield Label(f"y / Enter: {self.yes_label}    n / Esc: cancel", classes="hint")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class Prompt(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question: str, value: str = "", placeholder: str = "") -> None:
        super().__init__()
        self.question, self.value, self.placeholder = question, value, placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.question, classes="dialog-title")
            yield Input(value=self.value, placeholder=self.placeholder, id="prompt-input")
            yield Label("Enter accepts    Esc cancels", classes="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
