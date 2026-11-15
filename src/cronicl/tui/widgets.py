"""Small helpers shared by the screens."""
from __future__ import annotations

from rich.text import Text


def fit(text: Text, width: int) -> Text:
    """Cut `text` to `width` cells with an ellipsis (an OptionList wraps long rows instead of cutting them)."""
    text.truncate(max(10, width), overflow="ellipsis")
    return text


def room(app, margin: int = 4) -> int:
    """The columns a full-width list row can use on this terminal."""
    return max(30, app.size.width - margin)


def dialog_room(app) -> int:
    """The columns a row inside a dialog can use (the dialog is 72 wide, or 96% of a narrow terminal)."""
    return max(24, min(72, int(app.size.width * 0.96)) - 8)
