"""The key reference."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

HELP = """\
[b]Finding[/b]
  type          narrow the list: names, years, places; typos and accents are fine
  ↑ ↓           move              Enter  open the person
  Ctrl+N        a new person      F2     all warnings
  Esc           clear the search  Ctrl+Q quit

[b]On a person[/b]
  ↑ ↓           move through the record
  Enter         edit the line, open a relative, or expand a partner (its first row opens them)
  a             add a field, an event, a partner or a child (type to search)
  d             delete the line   o  open the partner
  Ctrl+E        edit this record as raw YAML
  w             warnings          Esc  leave (you see the changes first)

[b]Editing[/b]
  Enter saves a field; an empty value removes it; Esc cancels.
  Dates: F2 about · F3 before · F4 after · F5 between · F6 from–to · F7 unknown
  Long text and raw YAML: Ctrl+S saves.

[b]Writing[/b]
  Nothing is written until you confirm. The review shows exactly which lines change:
  Enter or y writes · n keeps editing · x discards everything.
  If a file changed on disk meanwhile, nothing is written and r reloads it.

[b]Warnings[/b]
  Enter jumps to the line · f shows a fix as a diff before anything changes.
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,enter,f1,question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide tall"):
            yield Label("cronicl keys", classes="dialog-title")
            with VerticalScroll():
                yield Static(HELP, id="help-text")
            yield Label("Esc closes", classes="hint")

    def action_close(self) -> None:
        self.dismiss(None)
