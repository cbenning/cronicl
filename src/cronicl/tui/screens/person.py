"""One person: their record as rows you can move through, then their family, then their warnings."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ...core.recordedit import EditRefused, remove, set_value
from ..recordview import Row, build
from .editors import PeoplePicker, editor_for


def row_text(row: Row, indent_extra: int = 0) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    pad = "  " * (row.depth + indent_extra)
    if row.comment_only:
        text.append(f"{pad}# {row.value}", style="dim italic")
        return text
    text.append(pad)
    if row.problems:
        text.append("⚠ ", style="bold red")
    if row.kind in ("group", "item"):
        text.append(f"{row.label}" if row.kind == "item" else f"{row.label}:", style="bold cyan" if row.kind == "group" else "dim")
        if row.value:
            text.append(f" {row.value}", style="dim")
    else:
        text.append(f"{row.label}:" if row.label != "-" else "-", style="cyan")
        text.append(f" {row.value}", style="red" if row.problems else "")
        if row.extra:
            text.append(f"  {row.extra}", style="dim")
    if row.comment:
        text.append(f"  # {row.comment}", style="dim italic")
    return text


class PersonScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("o", "open_partner", "Open partner"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(self, pid: str) -> None:
        super().__init__()
        self.pid = pid
        self.expanded: set[str] = set()
        self.targets: dict[str, tuple] = {}
        self.keep_path: tuple | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="person-head")
        yield OptionList(id="record")
        yield Footer()

    def on_mount(self) -> None:
        self.rebuild()
        self.query_one("#record", OptionList).focus()

    def refresh_content(self) -> None:
        widget = self.query_one("#record", OptionList)
        keep = None
        if widget.highlighted is not None and widget.option_count:
            keep = widget.get_option_at_index(widget.highlighted).id
        if self.pid in self.app.family.tree.people:
            self.rebuild(keep=keep)

    # ---- building the list ----------------------------------------------------------------------------------------
    @property
    def family(self):
        return self.app.family

    def _file_text(self, source: str) -> str:
        return self.family.files.get(source, "")

    def rebuild(self, keep: str | None = None) -> None:
        family = self.family
        person = family.tree.people[self.pid]
        head = f"[b]{person.display_name}[/b]  [dim]{family.years_of(self.pid)}[/dim]"
        from ...core.living import is_living

        if is_living(person, family.today, family.cutoff):
            head += "  [yellow]● living[/yellow]"
        head += f"   [dim]{self.pid}  {person.source}:{person.line}[/dim]"
        self.query_one("#person-head", Static).update(head)

        options: list[Option] = []
        self.targets = {}

        def add(text, target=None, disabled=False):
            option_id = f"o{len(options)}"
            if target is not None:
                self.targets[option_id] = target
            options.append(Option(text, id=option_id, disabled=disabled))

        issues = family.issues
        view = build(self._file_text(person.source), self.pid, issues, family.name_of)
        self.view = view
        for row in view.rows:
            add(row_text(row), ("row", row), disabled=row.comment_only)
        if not view.rows:
            add(Text("(nothing recorded yet: press a to add a field)", style="dim italic"), None, True)

        relations = family.relations
        parents = relations.parents.get(self.pid, [])
        add(Text("Family", style="bold underline"), None, True)
        if parents:
            add(Text("Parents", style="bold"), None, True)
            for pid in parents:
                add(self._person_line(pid), ("open", pid))
        for cid in relations.couples_of.get(self.pid, []):
            couple = relations.couples[cid]
            partner = next((p for p in couple.partners if p != self.pid), None)
            if partner is None:
                continue
            if "Partners" not in [str(o.prompt) for o in options if o.disabled]:
                add(Text("Partners", style="bold"), None, True)
            mark = "▾" if partner in self.expanded else "▸"
            summary = family.couple_summary(self.pid, partner)
            line = Text(no_wrap=True, overflow="ellipsis")
            line.append(f"  {mark} {family.name_of(partner)}", style="bold")
            line.append(f"  {summary}" if summary else "", style="dim")
            add(line, ("partner", partner))
            if partner in self.expanded:
                found = family.couple_key_text(self.pid, partner)
                if found:
                    key, source = found
                    couple_view = build(self._file_text(source), key, issues, family.name_of)
                    for row in couple_view.rows:
                        add(row_text(row, indent_extra=2), ("couple_row", partner, row), disabled=row.comment_only)
                else:
                    add(Text("      (no couple record yet)", style="dim italic"), None, True)
            kids = relations.kids.get(cid, [])
            for kid in kids:
                if "Children" not in [str(o.prompt) for o in options if o.disabled]:
                    add(Text("Children", style="bold"), None, True)
                add(self._person_line(kid), ("open", kid))
        siblings = sorted({c for p in parents for cid in relations.couples_of.get(p, []) for c in relations.kids.get(cid, []) if c != self.pid})
        if siblings:
            add(Text("Siblings", style="bold"), None, True)
            for sib in siblings:
                add(self._person_line(sib), ("open", sib))

        mine = family.issues_of(self.pid)
        if mine:
            add(Text("Warnings", style="bold underline"), None, True)
            for issue in mine:
                line = Text(no_wrap=True, overflow="ellipsis")
                line.append("⚠ ", style="bold red" if issue.severity == "error" else "bold yellow")
                line.append(f"{issue.code}", style="bold")
                line.append(f"  line {issue.line}  " if issue.line else "  ", style="dim")
                line.append(issue.message)
                add(line, ("warning", issue))

        widget = self.query_one("#record", OptionList)
        widget.clear_options()
        widget.add_options(options)
        first = next((i for i, o in enumerate(options) if not o.disabled), None)
        index = first
        if self.keep_path is not None:
            index = next((i for i, o in enumerate(options) if self._path_of(o) == self.keep_path), first)
            self.keep_path = None
        elif keep:
            index = next((i for i, o in enumerate(options) if o.id == keep), first)
        if index is not None:
            widget.highlighted = index

    def _path_of(self, option):
        target = self.targets.get(option.id)
        return getattr(target[-1], "path", None) if target else None

    def _person_line(self, pid: str) -> Text:
        family = self.family
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"    {family.name_of(pid) or pid}", style="bold")
        line.append(f"  {family.years_of(pid)}", style="dim")
        return line

    # ---- events ---------------------------------------------------------------------------------------------------
    def _target(self):
        widget = self.query_one("#record", OptionList)
        if widget.highlighted is None:
            return None
        return self.targets.get(widget.get_option_at_index(widget.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        target = self.targets.get(event.option.id)
        if target is None:
            return
        kind = target[0]
        if kind == "open":
            self.app.open_person(target[1])
        elif kind == "partner":
            partner = target[1]
            self.expanded.symmetric_difference_update({partner})
            self.rebuild(keep=event.option.id)
        elif kind == "warning":
            self._jump_to(target[1])
        elif kind in ("row", "couple_row"):
            self.edit_row(target)

    # ---- editing a row ---------------------------------------------------------------------------------------------
    def edit_row(self, target) -> None:
        row = target[-1]
        if row.kind in ("group", "item") or row.comment_only or not row.path:
            return
        record_key = row.path[0]
        source = self._source_of(target)
        if source is None:
            return
        screen = editor_for(self.app, record_key, row.path, row.value)
        if screen is None:
            self.app.notify("That line is edited with Ctrl+E (the raw record)", severity="warning")
            return
        self.app.push_screen(screen, lambda value, row=row, source=source: self._apply_row(row, source, value))

    def _source_of(self, target) -> str | None:
        if target[0] == "row":
            return self.family.tree.people[self.pid].source
        found = self.family.couple_key_text(self.pid, target[1])
        return found[1] if found else None

    def _apply_row(self, row: Row, source: str, value) -> None:
        if value is None:
            return
        if value == PeoplePicker.NEW:
            self.app.notify("New people are added from the field palette (a)", severity="warning")
            return
        session = self.app.session
        text = session.staged[source]
        try:
            new = remove(text, row.path) if value == "" else set_value(text, row.path, value)
        except EditRefused as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.keep_path = row.path
        session.stage(source, new)

    def _jump_to(self, issue) -> None:
        widget = self.query_one("#record", OptionList)
        for i in range(widget.option_count):
            target = self.targets.get(widget.get_option_at_index(i).id)
            if target and target[0] in ("row", "couple_row") and issue in target[-1].problems:
                widget.highlighted = i
                return

    def action_open_partner(self) -> None:
        target = self._target()
        if target and target[0] in ("partner", "couple_row"):
            self.app.open_person(target[1])

    def action_back(self) -> None:
        self.app.pop_screen()
