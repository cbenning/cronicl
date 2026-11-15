"""The Textual application: decides which screen to open first and owns the data folder."""
from __future__ import annotations

from pathlib import Path

from textual.app import App

from ..core.family import has_family
from ..core.store import load_tree


class CroniclApp(App):
    TITLE = "cronicl"

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = Path(data_dir)

    def on_mount(self) -> None:
        self.open_home()

    def open_home(self) -> None:
        """Show the finder when the family loads, else the screen that helps fix that."""
        from .screens.finder import FinderScreen
        from .screens.problem import ProblemScreen
        from .screens.start import StartScreen

        while len(self.screen_stack) > 1:
            self.pop_screen()
        tree, issues = load_tree(self.data_dir)
        old = (self.data_dir / "people").is_dir() and any((self.data_dir / "people").glob("*.md"))
        if not has_family(self.data_dir) and not old:
            self.push_screen(StartScreen())
            return
        blocking = [i for i in issues if i.code in ("E-BAD-FAMILY", "E-NO-FAMILY")]
        legacy_only = old and not has_family(self.data_dir)
        if blocking or legacy_only:
            self.push_screen(ProblemScreen(blocking or issues, old_layout=legacy_only))
            return
        self.push_screen(FinderScreen())
