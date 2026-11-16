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
    CSS_PATH = "theme.tcss"
    BINDINGS = [("f1", "help", "Help")]
    ENABLE_COMMAND_PALETTE = False  # the field palette (a) is ours; Textual's own would only confuse

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
    def open_person(self, pid: str, jump=None) -> None:
        from .screens.person import PersonScreen

        if self.family and pid in self.family.tree.people:
            self.push_screen(PersonScreen(pid, jump=jump))

    def new_person(self) -> None:
        """Ctrl+N in the finder: create a person (asking which file when the family is a folder) and open them."""
        from .screens.editors import ChoiceEditor

        files = sorted(self.session.staged)
        if len(files) > 1:
            self.push_screen(ChoiceEditor("Which file?", [(name, "") for name in files], files[0]), self._new_person_in)
        else:
            self._new_person_in(files[0] if files else "family.yml")

    def _new_person_in(self, source: str | None) -> None:
        if not source:
            return
        self.create_person(source, None, lambda pid: self.open_person(pid))

    def ask_person(self, then) -> None:
        """Ask for a new person's name and id; call `then(spec)` (a dict with id, given, surname) when they accept."""
        from .screens.newperson import NewPersonScreen

        def made(spec) -> None:
            if spec is not None:
                then(spec)

        self.push_screen(NewPersonScreen(self.session.family.taken_ids()), made)

    def stage_person(self, source: str, spec: dict, parents: list[str] | None = None) -> str:
        """Stage the new person's record at the end of `source`; return their id."""
        from ..core.recordedit import EditRefused, add_person_record
        from .session import Unreadable

        data: dict = {}
        name = {k: spec[k] for k in ("given", "surname") if spec[k]}
        if name:
            data["name"] = name
        if parents:
            data["parents"] = list(parents)
        try:
            self.session.stage(source, add_person_record(self.session.staged[source], spec["id"], data))
        except (EditRefused, Unreadable) as exc:
            self.notify(str(exc), severity="error")
            return None
        return spec["id"]

    def create_person(self, source: str, parents: list[str] | None, then) -> None:
        """Ask for a name, stage the new record in `source` (with `parents`), and call `then(new id)`."""
        def made(spec) -> None:
            new_id = self.stage_person(source, spec, parents)
            if new_id:
                then(new_id)

        self.ask_person(made)

    def action_help(self) -> None:
        self.open_help()

    async def action_quit(self) -> None:
        """Quit, but go through the diff first when something is staged."""
        if self.session is not None and self.session.changed:
            self.review_changes(lambda result: self.exit() if result != "back" else None)
        else:
            self.exit()

    def open_warnings(self) -> None:
        from .screens.warnings import WarningsScreen

        self.push_screen(WarningsScreen())

    def open_help(self) -> None:
        from .screens.help import HelpScreen

        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())
