# Pick several relatives in one go (TUI)

## Intent

Adding children or parents in the terminal app takes one trip through the palette and the picker per person. Adding three children means reopening the picker three times. The owner wants the picker to stay open so several people can be picked in a row: parents until there are two, children until Esc.

## Goals

- "Add a child" keeps the picker open after each pick, until Esc.
- "Add a parent" (and adoptive parent) keeps the picker open until the person has two parents of that kind, then closes itself.
- Each pick is staged straight away, so Esc ends the batch without losing anything already picked.

## Non-goals

- Partners stay single-pick.
- No undo inside the picker. Staged changes are still reviewed or discarded in the existing diff screen.
- No change to the web viewer, the CLI or the file format.

## Constraints

- Reuse `PeoplePicker` (`src/cronicl/tui/screens/editors.py`). Do not add a second picker.
- Single-pick callers (partner, editing an existing parent, `editor_for`) keep their current behaviour with no changes.
- A picked person must leave the list. The existing `exclude` set already hides linked people, so it is recomputed after each pick.

## Approaches

1. **Multi-pick mode inside `PeoplePicker` (chosen).** A flag turns Enter into "stage this one and stay open". The caller passes a callback that stages one link and says whether to stay open. Smallest change, one picker, and it fits the existing staging code.
2. **Checkbox list, confirm at the end.** Mark several rows, press a key to apply. Clearer for undoing a pick, but it adds a new interaction, hides what is staged, and goes against "until I hit escape".
3. **Re-open the picker automatically after each pick from the caller.** No picker change, but the screen flickers and loses the search text and cursor position on every pick.

## Design

- `PeoplePicker` gets an optional `on_pick` callback. When it is set, Enter calls it with the id, then refreshes the list and stays open. When it is not set, the picker behaves as today and dismisses with the id.
- `on_pick` returns whether the picker should close. For parents, the caller returns true once the person has two parents.
- A line at the top shows who has been added in this session of the picker (for example "Added: Ada, Bob"). The footer reads "Enter adds · Esc done".
- The `exclude` set grows with each pick, so the picked person leaves the list.
- "＋ New person…" keeps today's behaviour: it closes the picker and opens the nested new-person screen.
- A child who already has two parents is refused with the existing notification, and the picker stays open.
- Callers to change: `_add_child` and the parents branch of `_add_field` in `src/cronicl/tui/screens/person.py`.

## Left to the builder

- Exact wording and styling of the "Added" line.
- How the refreshed list keeps the search text and cursor position.
- Tests go under `tests/tui/`, written first, in the style of the existing palette and relationship tests.
