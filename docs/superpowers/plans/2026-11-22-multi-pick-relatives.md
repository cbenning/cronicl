# Pick several relatives at once Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the terminal app, "Add a child" and "Add a parent" keep the people picker open so several people can be picked in a row.

**Architecture:** `PeoplePicker` gets an optional `on_pick` callback. When set, Enter calls it with the picked id, adds that id to the picker's `exclude` set, refreshes the list and stays open; the callback's return value says whether to close. Callers stage the link inside the callback. When `on_pick` is not set the picker behaves exactly as before.

**Tech Stack:** Python 3.11+, Textual (`ModalScreen`, `OptionList`), pytest with Textual's Pilot (`tests/tui/conftest.py::drive`).

**Spec:** `docs/superpowers/specs/2026-11-22-multi-pick-relatives-design.md`

## Global Constraints

- Reuse `PeoplePicker` in `src/cronicl/tui/screens/editors.py`; no second picker class.
- Partner, "edit an existing parent" (`_apply_row`) and every other `PeoplePicker` caller keep single-pick behaviour with no code change.
- Each pick is staged immediately; Esc ends the batch and keeps what was picked. No undo in the picker.
- Footer text in multi-pick mode: `Enter adds · Esc done`. Line of picked names: `Added: Ada, Bob` (names from `family.name_of`, joined with `, `).
- "＋ New person…" keeps today's behaviour: the picker dismisses with `PeoplePicker.NEW`.
- A child who already has two parents is refused with the existing notification (`"<name> already has two parents"`, severity `warning`) and the picker stays open.
- Python 3.11 compatible; no new dependencies.

## Review Focus

- Typing in the search box after a pick still lists only people not yet picked (the exclude set persists across `_fill`).
- Picking the only remaining person leaves an empty list (only "＋ New person…" when allowed); Enter must not crash.
- A pick whose staging is refused (`EditRefused`/`Unreadable`) does not add the person to "Added" and keeps the picker open.
- Parent with one existing parent closes after exactly one pick; parent with none closes after exactly two.
- Adoptive parents count separately from birth parents.

---

### Task 1: Multi-pick mode in `PeoplePicker`, used by "Add a child"

**Files:**
- Modify: `src/cronicl/tui/screens/editors.py:198-250` (`PeoplePicker`)
- Modify: `src/cronicl/tui/screens/person.py:513-535` (`_add_child`, `_existing_child`)
- Test: `tests/tui/test_relationships.py`

**Interfaces:**
- Produces: `PeoplePicker.__init__(self, title: str, family, exclude: set[str], allow_new: bool = True, current: str = "", on_pick: Callable[[str], bool] | None = None)`. `on_pick(pid)` returns `True` to close the picker (it then dismisses with `None`), `False` to stay open. The picker adds `pid` to `self.exclude` and to its "Added" line only when `on_pick` returned without raising and the link was made (see `on_pick` contract below).
- Produces: `PersonScreen._existing_child(self, child: str) -> bool` returns `True` when the link was staged, `False` when refused.
- `on_pick` contract: it returns `True` to close, `False` to stay open. To tell the picker a pick failed, the callback returns `None`; the picker then neither excludes nor lists that person and stays open.

- [ ] **Step 1: Write the failing tests** in `tests/tui/test_relationships.py`, using `FAMILY_PLUS` extended with a third person (`third-person`, given `Third`, surname `Person`) and the existing `open_person`, `palette_pick`, `highlight`, `option_texts`, `texts`, `screen_name` helpers:
  - `test_add_a_child_keeps_the_picker_open_until_escape`: open `lovelace-ada`, `palette_pick(pilot, "child")`, highlight "Other Person" in `#people`, Enter; assert `screen_name(app) == "PeoplePicker"`, `"Other Person"` not in `option_texts(app, "#people")`, `"Added: Other Person"` in `texts(app)`; highlight "Third Person", Enter; press Escape; assert `screen_name(app) == "PersonScreen"` and `staged(app)` contains both `other-person:\n  name: {given: Other, surname: Person}\n  parents: [lovelace-ada]` and the same for `third-person`.
  - `test_the_added_line_lists_everyone_picked_so_far`: after two picks, `"Added: Other Person, Third Person"` in `texts(app)`.
  - `test_a_child_with_two_parents_is_refused_and_the_picker_stays_open`: give `third-person` `parents: [byron-george, milbanke-annabella]` in the family text; open `lovelace-ada`, `palette_pick("child")`, highlight "Third Person", Enter; assert the screen is still `PeoplePicker`, `staged(app)` is unchanged, and `"Added:"` is not in `texts(app)`.
  - `test_search_text_still_hides_people_already_picked`: pick "Other Person", then `type_text(pilot, "Person")`; assert `"Other Person"` not in `option_texts(app, "#people")` and `"Third Person"` in it.
  - `test_picking_the_last_person_leaves_only_new_person`: with `other-person` as the only candidate (no `third-person`), pick it; assert `option_texts(app, "#people")` is `["＋ New person…"]`, then press Escape and assert `screen_name(app) == "PersonScreen"` (no crash).
  - `test_the_partner_picker_still_closes_after_one_pick`: open `lovelace-ada`, `palette_pick("partner")`, highlight "Other Person", Enter; assert `screen_name(app) != "PeoplePicker"`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/tui/test_relationships.py -k "keeps_the_picker_open or added_line or two_parents_is_refused or search_text_still or last_person or partner_picker_still" -q`
Expected: the multi-pick tests FAIL (picker closes after one pick); the partner test passes.

- [ ] **Step 3: Implement multi-pick in `PeoplePicker`** (`editors.py`): add the `on_pick` constructor argument and store `self.on_pick`, `self.picked: list[str]`. In `compose`, add `Label("", id="people-added", classes="hint")` between the input and the list, and make the footer `Label` read `Enter adds · Esc done` when `on_pick` is set, else the current text. In `_pick`: if `on_pick` is set and the highlighted id is not `NEW`, call `self.on_pick(id)`; on `None` do nothing more; on `True` dismiss `None`; on `False` add the id to `self.exclude` and `self.picked`, update the `#people-added` text to `Added: ` + names via `self.family.name_of`, keep the query text and call `_fill(query)`. `NEW` and the no-`on_pick` path dismiss with the id as today. Hide `#people-added` (set `display = False`) while `self.picked` is empty.

- [ ] **Step 4: Use it for children** (`person.py`): `_add_child` builds `PeoplePicker("Add a child", family, exclude, True, on_pick=self._pick_child)` where `_pick_child(pid) -> bool | None` calls `_existing_child(pid)` and returns `None` if that returned `False`, else `False` (a child pick never closes the picker). `picked(value)` keeps handling `None` and `NEW` only. `_existing_child` returns `False` after the two-parents notification or when `_stage` returns `False`, else `True`.

- [ ] **Step 5: Run the new tests and the whole TUI suite**

Run: `uv run pytest tests/tui -q -n auto`
Expected: all pass. Existing tests that picked one child and then asserted on the next screen may need a trailing `await pilot.press("escape")` before their assertions; add it where the failure shows the picker still open.

- [ ] **Step 6: Commit**

```bash
git add src/cronicl/tui/screens/editors.py src/cronicl/tui/screens/person.py tests/tui/test_relationships.py
git commit -m "feat(tui): pick several children without reopening the picker"
```

---

### Task 2: "Add a parent" picks up to two, then closes

**Files:**
- Modify: `src/cronicl/tui/screens/person.py:375-400` (`_add_field`, parents branch)
- Test: `tests/tui/test_relationships.py`
- Modify: `CHANGELOG.md` (Unreleased), `README.md:87`

**Interfaces:**
- Consumes: `PeoplePicker(..., on_pick=...)` and the `True`/`False`/`None` return contract from Task 1.
- Produces: no new public names.

- [ ] **Step 1: Write the failing tests** in `tests/tui/test_relationships.py` (family: `FAMILY_PLUS` plus `third-person`):
  - `test_adding_parents_closes_the_picker_after_the_second`: open `other-person` (no parents), `palette_pick(pilot, "parents")`, highlight "Third Person", Enter, assert still `PeoplePicker`; highlight "George Byron", Enter; assert `screen_name(app) == "PersonScreen"` and `staged(app)` contains `parents: [third-person, byron-george]` (order as picked).
  - `test_a_person_with_one_parent_closes_the_picker_after_one_more`: give `other-person` `parents: [byron-george]` in the family text, `palette_pick("parents")`, pick "Annabella Milbanke"; assert `screen_name(app) == "PersonScreen"` and `parents: [byron-george, milbanke-annabella]`.
  - `test_escape_after_the_first_parent_keeps_it`: pick one parent, press Escape; assert `parents: [third-person]` and `screen_name(app) == "PersonScreen"`.
  - `test_adoptive_parents_are_counted_apart_from_birth_parents`: `other-person` with `parents: [byron-george, milbanke-annabella]`; `palette_pick("adoptive-parents")`; pick "Third Person"; assert the picker is still open (adoptive count is 1, not 2).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/tui/test_relationships.py -k "adding_parents or one_parent_closes or escape_after_the_first or adoptive_parents_are_counted" -q`
Expected: FAIL (picker closes after the first pick).

- [ ] **Step 3: Implement** in `_add_field`: for `field.path in ("parents", "adoptive-parents")`, set `screen.on_pick` (the screen returned by `editor_for`) to a closure `(pid) -> bool | None` that stages `list_add(t, (key, field.path), pid)` via `self._stage(source, ..., (key, field.path, 0))`, returns `None` when `_stage` returns `False`, and otherwise returns `True` when `len(record_data(self.app.session.staged[source], key).get(field.path) or []) >= 2`, else `False`. The existing `done(value, ...)` callback keeps handling `PeoplePicker.NEW` (and `None`); its direct-id branch stays for safety but is no longer reached for these fields.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q -n auto`
Expected: all pass (about 1510 tests).

- [ ] **Step 5: Document and commit.** Add under `## Unreleased` in `CHANGELOG.md`: `- New: in the terminal app, "Add a child" keeps the picker open so you can pick several children in a row (Esc when done), and "Add a parent" lets you pick both parents before it closes.` In `README.md` line 87, add one sentence saying the child and parent pickers stay open for more picks.

```bash
git add src/cronicl/tui/screens/person.py tests/tui/test_relationships.py CHANGELOG.md README.md
git commit -m "feat(tui): pick both parents in one go"
```
