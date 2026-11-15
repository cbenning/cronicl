"""Every warning `check` reports, grouped by person; jump to one, or apply its fix after a look at the diff."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Label, OptionList
from textual.widgets.option_list import Option

from ...core.fixes import fix_options
from .editors import ChoiceEditor


class WarningsScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("f", "fix", "Fix"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.targets: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        yield Label("", id="warnings-title")
        yield OptionList(id="warnings")
        yield Label("", id="warnings-empty", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_content()
        self.query_one("#warnings", OptionList).focus()

    def refresh_content(self) -> None:
        family = self.app.family
        groups: dict[str, list] = {}
        for issue in family.issues:
            owners = family.owners(issue)
            label = ", ".join(family.name_of(p) or p for p in owners) if owners else (issue.path or "the family")
            groups.setdefault(label, []).append(issue)
        options: list[Option] = []
        self.targets = {}
        for label in sorted(groups, key=str.casefold):
            options.append(Option(Text(label, style="bold underline"), id=f"g{len(options)}", disabled=True))
            for issue in groups[label]:
                line = Text(no_wrap=True, overflow="ellipsis")
                line.append("  ⚠ ", style="bold red" if issue.severity == "error" else "bold yellow")
                line.append(issue.code, style="bold")
                line.append(f"  line {issue.line}  " if issue.line else "  ", style="dim")
                line.append(issue.message)
                option_id = f"i{len(options)}"
                self.targets[option_id] = issue
                options.append(Option(line, id=option_id))
        widget = self.query_one("#warnings", OptionList)
        keep = widget.highlighted
        widget.clear_options()
        widget.add_options(options)
        first = next((i for i, o in enumerate(options) if not o.disabled), None)
        if keep is not None and keep < len(options) and not options[keep].disabled:
            widget.highlighted = keep
        elif first is not None:
            widget.highlighted = first
        count = sum(len(v) for v in groups.values())
        self.query_one("#warnings-title", Label).update(f"{count} {'warning' if count == 1 else 'warnings'}" if count else "")
        self.query_one("#warnings-empty", Label).update("" if count else "No warnings. The family file is clean.")

    def _issue(self):
        widget = self.query_one("#warnings", OptionList)
        if widget.highlighted is None or not widget.option_count:
            return None
        return self.targets.get(widget.get_option_at_index(widget.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        issue = self.targets.get(event.option.id)
        if issue is None:
            return
        owners = self.app.family.owners(issue)
        if not owners:
            self.app.notify(f"{issue.path or 'This'} is not a person's record; open it in an editor", severity="warning")
            return
        self.app.open_person(owners[0], jump=issue)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_fix(self) -> None:
        issue = self._issue()
        if issue is None:
            return
        session = self.app.session
        options = fix_options(self.app.family.tree, session.staged, issue)
        if not options:
            self.app.notify(f"No automatic fix for {issue.code}. Enter opens the person.", severity="warning")
            return
        if len(options) == 1:
            self._apply(options[0])
            return
        labels = [o.label for o in options]
        default = next((o.label for o in options if o.default), "")
        chooser = ChoiceEditor(f"{issue.code}: how should it be fixed?", [(label, "") for label in labels], default)
        self.app.push_screen(chooser, lambda label: self._chosen(options, label))

    def _chosen(self, options, label) -> None:
        for option in options:
            if option.label == label:
                self._apply(option)
                return

    def _apply(self, option) -> None:
        session = self.app.session
        snapshot = session.snapshot()
        for name, text in option.files.items():
            session.stage(name, text)

        def reviewed(result: str) -> None:
            if result == "back":
                session.restore(snapshot)  # the fix was only proposed: take it back out

        self.app.review_changes(reviewed)
