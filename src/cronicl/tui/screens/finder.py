"""The finder (placeholder until the finder task replaces it)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static


class FinderScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Static("finder", id="finder-placeholder")
        yield Footer()
