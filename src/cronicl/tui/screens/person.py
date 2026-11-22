"""One person: their record as rows you can move through, then their family, then their warnings."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ...core.catalog import FIELDS
from ..session import Unreadable
from ...core.recordedit import EditRefused, add_couple_event, add_couple_record, couple_key, list_add, record_data, remove, set_value
from ..recordview import Row, build
from ..widgets import fit, room
from .editors import ChoiceEditor, PeoplePicker, TextEditor, ancestors, catalog_key, descendants, editor_for
from .modals import Confirm, Prompt
from .palette import VALUE_EVENT_TYPES, PaletteScreen, build_entries
from .raw import RawScreen


def row_text(row: Row, indent_extra: int = 0, width: int = 80) -> Text:
    text = Text(no_wrap=True)
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
    return fit(text, width)


class PersonScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("a", "palette", "Add field"),
        Binding("d", "delete", "Delete line"),
        Binding("ctrl+e", "raw", "Raw YAML"),
        Binding("w", "warnings", "Warnings"),
        Binding("question_mark", "app.help", "Help", show=False),
        Binding("o", "open_partner", "Open partner"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(self, pid: str, nested: bool = False, jump=None) -> None:
        super().__init__()
        self.pid = pid
        self.jump = jump  # an issue to put the cursor on when the screen opens
        self.nested = nested  # opened from another person's edit: Esc goes back without the diff
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
        if self.jump is not None:
            self._jump_to(self.jump)

    def on_resize(self, event) -> None:
        if self.is_mounted:
            self.refresh_content()

    def on_screen_resume(self) -> None:
        if self.app.family is not None and self.pid not in self.app.family.tree.people:
            self.app.call_after_refresh(self._vanish)

    def _vanish(self) -> None:
        """This person no longer exists (their staged record was discarded or the file changed): close the screen."""
        if self is self.app.screen:
            self.app.pop_screen()

    def refresh_content(self) -> None:
        widget = self.query_one("#record", OptionList)
        if self.pid not in self.app.family.tree.people:
            if self is self.app.screen:
                self.app.call_after_refresh(self._vanish)
            return
        keep = None
        if widget.highlighted is not None and widget.option_count:
            keep = widget.get_option_at_index(widget.highlighted).id
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
            add(row_text(row, 0, room(self.app)), ("row", row), disabled=row.comment_only)
        if not view.rows:
            add(Text("(nothing recorded yet: press a to add a field)", style="dim italic"), None, True)

        relations = family.relations
        parents = relations.parents.get(self.pid, [])
        add(Text("Family", style="bold underline"), None, True)
        adoptive = relations.adoptive_parents.get(self.pid, [])
        if parents:
            add(Text("Adoptive parents" if adoptive else "Parents", style="bold"), None, True)
            for pid in parents:
                add(self._person_line(pid), ("open", pid))
        birth = relations.birth_parents.get(self.pid, [])
        if adoptive and birth:
            add(Text("Birth parents", style="bold"), None, True)
            for pid in birth:
                add(self._person_line(pid), ("open", pid))
        for cid in relations.couples_of.get(self.pid, []):
            couple = relations.couples[cid]
            partner = next((p for p in couple.partners if p != self.pid), None)
            if partner is not None:  # a lone parent's children have no partner line
                if "Partners" not in [str(o.prompt) for o in options if o.disabled]:
                    add(Text("Partners", style="bold"), None, True)
                mark = "▾" if partner in self.expanded else "▸"
                summary = family.couple_summary(self.pid, partner)
                line = Text(no_wrap=True)
                line.append(f"  {mark} {family.name_of(partner)}", style="bold")
                line.append(f"  {summary}" if summary else "", style="dim")
                add(fit(line, room(self.app)), ("partner", partner))
                if partner in self.expanded:
                    go = Text(no_wrap=True)
                    go.append(f"      Open {family.name_of(partner) or partner} \u203a", style="bold cyan")
                    add(fit(go, room(self.app)), ("open", partner))
                    found = family.couple_key_text(self.pid, partner)
                    if found:
                        key, source = found
                        couple_view = build(self._file_text(source), key, issues, family.name_of)
                        for row in couple_view.rows:
                            add(row_text(row, 2, room(self.app)), ("couple_row", partner, row), disabled=row.comment_only)
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
                line = Text(no_wrap=True)
                line.append("⚠ ", style="bold red" if issue.severity == "error" else "bold yellow")
                line.append(f"{issue.code}", style="bold")
                line.append(f"  line {issue.line}  " if issue.line else "  ", style="dim")
                line.append(issue.message)
                add(fit(line, room(self.app)), ("warning", issue))

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
        line = Text(no_wrap=True)
        line.append(f"    {family.name_of(pid) or pid}", style="bold")
        line.append(f"  {family.years_of(pid)}", style="dim")
        return fit(line, room(self.app))

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
            self._leave(lambda pid=target[1]: self.app.open_person(pid))
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
        screen = editor_for(self.app, record_key, row.path, row.raw or row.value)
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
            self._new_parent(lambda pid: self._stage(source, lambda t: set_value(t, row.path, pid), row.path))
            return
        build = (lambda t: remove(t, row.path)) if value == "" else (lambda t: set_value(t, row.path, value))
        self._stage(source, build, row.path)

    def _jump_to(self, issue) -> None:
        widget = self.query_one("#record", OptionList)
        for i in range(widget.option_count):
            target = self.targets.get(widget.get_option_at_index(i).id)
            if target and target[0] in ("row", "couple_row") and any((p.code, p.line) == (issue.code, issue.line) for p in target[-1].problems):
                widget.highlighted = i
                return

    def action_warnings(self) -> None:
        self.app.open_warnings()

    def action_open_partner(self) -> None:
        target = self._target()
        if target and target[0] in ("partner", "couple_row"):
            self._leave(lambda pid=target[1]: self.app.open_person(pid))

    def _leave(self, then) -> None:
        """Run `then` (leave this person) once any staged changes have been written or discarded."""
        if self.app.session.changed:
            self.app.review_changes(lambda result: then() if result != "back" else None)
        else:
            then()

    def action_back(self) -> None:
        if self.nested:
            self.app.pop_screen()
            return
        self._leave(self.app.pop_screen)

    # ---- which record the cursor is in -------------------------------------------------------------------------------
    def _record_context(self):
        """("person", key, source) or ("couple", partner, key, source) for the highlighted line."""
        target = self._target()
        person = self.family.tree.people[self.pid]
        if target and target[0] in ("partner", "couple_row"):
            partner = target[1]
            found = self.family.couple_key_text(self.pid, partner)
            if found:
                return ("couple", partner, found[0], found[1])
            return ("couple", partner, couple_key(self.pid, partner), person.source)
        return ("person", None, self.pid, person.source)

    def _stage(self, source: str, build, keep_path: tuple | None = None) -> bool:
        try:
            new = build(self.app.session.staged[source])
            if new == self.app.session.staged[source]:
                return True  # nothing would change
            self.keep_path = keep_path
            self.app.session.stage(source, new)
        except (EditRefused, Unreadable) as exc:
            self.keep_path = None
            self.app.notify(str(exc), severity="error")
            return False
        return True

    # ---- the field palette -------------------------------------------------------------------------------------------
    def action_palette(self) -> None:
        kind, partner, key, source = self._record_context()
        present: set[tuple] = set()
        parent_count = 0
        text = self.app.session.staged[source]
        try:
            data = record_data(text, key)
        except EditRefused:
            data = {}
        for name, value in data.items():
            present.add((name,))
            if isinstance(value, dict):
                present.update((name, sub) for sub in value)
        for name in ("birth", "death"):
            if isinstance(data.get(name), str):
                present.add((name, "date"))  # a bare date is the date part
        parent_count = len(data.get("parents") or [])
        adoptive_count = len(data.get("adoptive-parents") or [])
        event_index = event_has = None
        target = self._target()
        if target and target[0] in ("row", "couple_row") and len(target[-1].path) >= 3 and target[-1].path[1] == "events" and isinstance(target[-1].path[2], int):
            event_index = target[-1].path[2]
            events = data.get("events") or []
            if event_index < len(events) and isinstance(events[event_index], dict):
                event_has = set(events[event_index])
        entries = build_entries(kind, present, parent_count, event_index, event_has, adoptive_count)
        title = f"Add to {self.family.name_of(self.pid)}" if kind == "person" else f"Add to the couple {self.family.name_of(self.pid)} + {self.family.name_of(partner)}"
        self.app.push_screen(PaletteScreen(title, entries), lambda action: self._palette_chosen(action, (kind, partner, key, source)))

    def _palette_chosen(self, action, context) -> None:
        if action is None:
            return
        kind, partner, key, source = context
        name = action[0]
        if name == "field":
            self._add_field(action[1], key, source)
        elif name == "event":
            self._add_event(action[1], context)
        elif name == "event_field":
            index, sub = action[1], action[2]
            self._ask_event_fields(key, source, index, [sub])
        elif name == "custom":
            self.app.push_screen(Prompt("Name of your field (it starts with x-)", placeholder="x-nickname"), lambda k: self._custom_key(k, key, source))
        elif name == "partner":
            self._add_partner()
        elif name == "child":
            self._add_child()

    def _add_field(self, field, key: str, source: str) -> None:
        steps = tuple(field.path.split("."))
        if field.path in ("birth", "death"):
            steps = (field.path, "date")
        elif field.path in ("parents", "adoptive-parents"):
            steps = (field.path, 0)
        path = (key, *steps)
        screen = editor_for(self.app, key, path, "")
        if screen is None:
            return

        def done(value, path=path, field=field) -> None:
            if not value:
                return
            if field.path in ("parents", "adoptive-parents"):
                if value == PeoplePicker.NEW:
                    self._new_parent(lambda pid: self._stage(source, lambda t: list_add(t, (key, field.path), pid), (key, field.path, 0)))
                    return
                self._stage(source, lambda t: list_add(t, (key, field.path), value), (key, field.path, 0))
            elif field.path == "name.also":
                self._stage(source, lambda t: list_add(t, (key, "name", "also"), value))
            else:
                self._stage(source, lambda t: set_value(t, path, value), path)

        self.app.push_screen(screen, done)

    def _add_event(self, slug: str, context) -> None:
        kind, partner, key, source = context
        event = {"type": slug}
        if kind == "couple":
            a, b = (self.pid, partner)
            found = self.family.couple_key_text(a, b)
            if found is None:
                build = lambda t: add_couple_event(t, a, b, event)  # noqa: E731
                key = couple_key(a, b)
            else:
                build = lambda t: list_add(t, (key, "events"), event)  # noqa: E731
        else:
            build = lambda t: list_add(t, (key, "events"), event)  # noqa: E731
        if not self._stage(source, build):
            return
        events = record_data(self.app.session.staged[source], key).get("events") or []
        index = len(events) - 1
        order = (["value"] if slug in VALUE_EVENT_TYPES else []) + ["date", "place"]
        self._ask_event_fields(key, source, index, order)

    def _ask_event_fields(self, key: str, source: str, index: int, remaining: list[str], finish=None) -> None:
        if not remaining:
            if finish:
                finish()
            return
        field, rest = remaining[0], remaining[1:]
        path = (key, "events", index, field)
        screen = editor_for(self.app, key, path, "")

        def done(value) -> None:
            if value is None:
                return
            if value:
                self._stage(source, lambda t: set_value(t, path, value), path)
            self._ask_event_fields(key, source, index, rest, finish)

        self.app.push_screen(screen, done)

    def _custom_key(self, name: str | None, key: str, source: str) -> None:
        if not name:
            return
        if not name.lower().startswith(("x-", "x_")):
            self.app.notify("Your own fields start with x- so they are never reported", severity="warning")
            return
        path = (key, name)
        self.app.push_screen(
            TextEditor(name, ""), lambda value: value and self._stage(source, lambda t: set_value(t, path, value), path)
        )

    # ---- delete and raw ----------------------------------------------------------------------------------------------
    def action_delete(self) -> None:
        target = self._target()
        if not target or target[0] not in ("row", "couple_row"):
            return
        row = target[-1]
        if row.comment_only or not row.path or len(row.path) < 2:
            return
        source = self._source_of(target)
        label = f"{row.label} {row.value}".strip() if row.kind != "group" else row.label
        what = f"“{label}” and everything under it" if row.kind in ("group", "item") else f"“{label}”"
        self.app.push_screen(Confirm(f"Remove {what}?", "Remove"), lambda yes, row=row, source=source: yes and self._stage(source, lambda t: remove(t, row.path)))

    def action_raw(self) -> None:
        kind, partner, key, source = self._record_context()
        self.app.push_screen(RawScreen(self.app.session, key, source))

    # ---- relationships -----------------------------------------------------------------------------------------------
    def _own_source(self) -> str:
        return self.family.tree.people[self.pid].source

    def _open_nested(self, pid: str) -> None:
        self.app.push_screen(PersonScreen(pid, nested=True))

    def _new_parent(self, then) -> None:
        """Create a person with no parents, call `then(new id)` to link them, and open them nested."""

        def made(pid: str) -> None:
            then(pid)
            self._open_nested(pid)

        self.app.create_person(self._own_source(), None, made)

    def _add_partner(self) -> None:
        family = self.family
        relations = family.relations
        children = {k for cid in relations.couples_of.get(self.pid, []) for k in relations.kids.get(cid, [])}
        exclude = {self.pid} | set(relations.parents.get(self.pid, [])) | children | {p for cid in relations.couples_of.get(self.pid, []) for p in relations.couples[cid].partners}

        def picked(value) -> None:
            if value is None:
                return
            if value == PeoplePicker.NEW:
                self.app.create_person(self._own_source(), None, lambda pid: self._partner_chosen(pid, True))
            else:
                self._partner_chosen(value, False)

        self.app.push_screen(PeoplePicker("Add a partner", family, exclude, True), picked)

    def _partner_chosen(self, other: str, created: bool) -> None:
        source = self._own_source()
        key = couple_key(self.pid, other)
        if not self._stage(source, lambda t: add_couple_event(t, self.pid, other, {"type": "marriage"})):
            return
        self.expanded.add(other)
        events = record_data(self.app.session.staged[source], key).get("events") or []
        index = len(events) - 1
        finish = (lambda: self._open_nested(other)) if created else None
        self.keep_path = None
        self._ask_event_fields(key, source, index, ["date", "place"], finish)

    def _add_child(self) -> None:
        family = self.family
        relations = family.relations
        children = {k for cid in relations.couples_of.get(self.pid, []) for k in relations.kids.get(cid, [])}
        exclude = {self.pid} | ancestors(family, self.pid) | children

        def picked(value) -> None:
            if value == PeoplePicker.NEW:  # existing people are linked as they are picked, in pick_child
                self._new_child()

        def pick_child(pid: str) -> bool | None:
            return False if self._existing_child(pid) else None  # a child pick never closes the picker: Esc does

        self.app.push_screen(PeoplePicker("Add a child", family, exclude, True, on_pick=pick_child), picked)

    def _existing_child(self, child: str) -> bool:
        """Make `child` a child of this person; False when that was refused."""
        family = self.family
        person = family.tree.people[child]
        if len(person.parents) >= 2:
            self.app.notify(f"{family.name_of(child)} already has two parents", severity="warning")
            return False
        return self._stage(person.source, lambda t: list_add(t, (child, "parents"), self.pid), (child, "parents", 0))

    def _new_child(self) -> None:
        family = self.family
        partners = [p for cid in family.relations.couples_of.get(self.pid, []) for p in family.relations.couples[cid].partners if p != self.pid]
        source = self._own_source()
        def named(spec) -> None:
            if not partners:
                self._open_nested(self.app.stage_person(source, spec, [self.pid]))
                return

            def other_parent(value) -> None:
                if value is None:
                    return
                parents = [self.pid] + ([value] if value else [])
                self._open_nested(self.app.stage_person(source, spec, parents))

            self.app.push_screen(
                ChoiceEditor("Other parent", [(p, family.name_of(p)) for p in partners], "", blank="(none)"), other_parent
            )

        self.app.ask_person(named)
