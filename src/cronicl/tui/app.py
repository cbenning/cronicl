"""The Textual application: decides which screen to open first and owns the data folder."""
from __future__ import annotations

from pathlib import Path

from textual.app import App

from ..core.family import has_family
from ..core.store import load_tree
from .model import Family
from .session import Session


class CroniclApp(App):
    TITLE = "cronicl"

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = Path(data_dir)
        self.session: Session | None = None

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
        self.session = Session(self.data_dir)
        self.session.on_change = self.refresh_screens
        self.push_screen(FinderScreen())

    @property
    def family(self) -> Family | None:
        return self.session.family if self.session else None

    def refresh_screens(self) -> None:
        """Tell every open screen the family changed (an edit was staged, discarded or written)."""
        for screen in self.screen_stack:
            refresh = getattr(screen, "refresh_content", None)
            if refresh and screen.is_attached:
                refresh()

    def review_changes(self, then) -> None:
        """Show the diff of everything staged and call `then` with: nothing, written, back, discarded or reloaded."""
        from .screens.diff import DiffScreen

        if not self.session.changed:
            then("nothing")
            return
        self.push_screen(DiffScreen(self.session), then)

    # ---- navigation the screens call; later tasks give them bodies --------------------------------------------------
    def open_person(self, pid: str) -> None:
        from .screens.person import PersonScreen

        if self.family and pid in self.family.tree.people:
            self.push_screen(PersonScreen(pid))

    def new_person(self) -> None:
        self.notify("New person comes with the editing screens")

    def open_warnings(self) -> None:
        self.notify("Warnings screen comes later")

    def open_help(self) -> None:
        self.notify("Help comes later")
