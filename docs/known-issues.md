# Known issues

Small defects that were found, judged not worth blocking a release, and left unfixed on purpose. Each entry says what
happens, what it costs the owner, and where the code is. Fix one by writing a test that fails first.

## GEDCOM export and import

### `CONC` lines split at a fixed 200 characters

`export-gedcom` continues a long value with `CONC` lines of exactly 200 characters, even when that cuts through the
middle of a word or just before a space. The GEDCOM 5.5.1 rule is that a reader must join `CONC` pieces with nothing
between them, so a correct reader restores the text exactly. Some old programs trim a leading space on a `CONC` line
and would lose that space. The cost is a missing space in a very long note in such a program. Code:
`_CHUNK` and `_Export.line` in `src/cronicl/core/gedcom_export.py`.

### `NPFX` / `NSFX` without `GIVN` doubles the prefix on import

A name like `1 NAME Dr. John /Smith/ Jr.` with `2 NPFX Dr.` and `2 NSFX Jr.` but no `2 GIVN` imports with the given
name `Dr. John` and the prefix `Dr.`, so the person is shown as "Dr. Dr. John Smith Jr.". The suffix is not doubled.
Files from programs that always write `GIVN` are not affected. Code: `_parse_name` in `src/cronicl/core/gedcom.py`.

### A second `NAME` with `TYPE married` loses its type and surname part

The importer keeps a second `NAME` as a plain "also known as" entry. Its `TYPE married` and the split into given name
and surname are dropped, and export writes it back as an `aka` name. The text of the name is kept, so search still
finds it; only the "married name" label is lost. Code: `_other_name` in `src/cronicl/core/gedcom.py`.

### Note text shaped like `@word@` is read as a pointer on import

A note that really contains text such as `@home@` is exported with the `@` doubled (`@@home@@`), which is correct, but
a file written by another program that leaves it single is read as a pointer to a record and the text is lost. The
GEDCOM rule says a literal `@` must be doubled, so files that follow it are not affected. Code: `_LINE` in
`src/cronicl/core/gedcom.py`.

### A `value` on an event that takes none is dropped without a warning

Events such as `burial` or `baptism` have no value in GEDCOM. If an owner writes a `value:` on one in `family.yml`,
export leaves it out and does not say so. Occupation, residence and the other value-carrying events are not affected.
Code: the `takes_value` branch in `src/cronicl/core/gedcom_export.py`.

## noindex

### `check` never warns `W-NOINDEX-FILE`

When `noindex: true` is set and the output folder already holds a `robots.txt` or `_headers` that cronicl did not
write, `build` leaves the file alone and prints `W-NOINDEX-FILE`. `check` cannot print it because it never looks at
the output folder. The owner learns it only from `build`. Code: `_write_noindex_files` in
`src/cronicl/site/render.py`.

## Couple events

### A couple's events other than marriage, divorce and the like are not shown on the site

Any event `type` is allowed in a couple record (`residence`, `census`, ...). They are kept in `family.yml`, survive
`rename` and the editing commands, and are written to GEDCOM as `EVEN`, but the person pages and the timeline do not
show them. On re-import they come back as set-aside lines, not as couple events. Code: `partnerships_from_events` in
`src/cronicl/core/family.py` keeps only beginning and ending events.

### Other keys of a couple event are not exported

Of a couple's extra events, GEDCOM export writes the type, `value`, `date`, `place`, `note` and `cite`. Your own `x-`
keys under such an event stay in `family.yml` and are not exported. The same events come back on re-import as
set-aside lines, and a second export drops them again with `W-GEDCOM-EXTRA-FAM`, so exporting, importing and
exporting again is not a round trip for them.

## Tree layout

### One marriage between relatives drops the sibling rule for the whole connected tree

When a marriage such as an uncle and a niece makes the strict layout impossible, the tree views stop keeping sibling
groups on one row for the whole connected family, not only for the groups involved. Nothing overlaps and nothing is
lost, but unrelated siblings can end up on different rows. Code: `_generations` in `src/cronicl/core/generations.py`.

### Some connectors still cross, and a short branch can hang high above its children

The order of each row comes from the average position of a block's parents and children; nothing counts crossings and
swaps neighbours to remove them, and a married couple is placed between the two families it joins, so it can sit away
from both sibling groups. A 156-person tree is left with about 15 crossings.

A couple with no parents in the tree is moved down to the row above their children. A couple that has recorded
parents is not: when their children sit several rows lower (one of them married into a longer line), the connector
runs through the rows between, and the couple's own parents stay above them. Lowering that whole branch needs the rows
chosen for the shortest total connector length instead of counted from the top. Code: `_layout_connected` and
`_lower_founders` in `src/cronicl/site/layout.py`.

## The TUI

- **Esc in the long-text editor or the raw pane drops what you typed without asking.** The diff step protects the file, but text typed into a box and cancelled is gone.
- **A date warning other than a death has no one-key fix.** `W-DATE-UNPARSED` on a birth or event date is only a jump to the line; open the field with Enter to retype it.
- **A file that ends with a YAML document-end marker (`...`).** New records are appended after the marker and the result does not parse; the TUI refuses the edit (the text is checked before it is staged) instead of writing it.
- **Two records with the same key.** The editor changes the first one while the reader uses the later one; the checker already reports `E-DUPLICATE-ID`, so fix that first.
- **Records with YAML anchors or aliases cannot be edited field by field.** The TUI says so and offers the raw pane (Ctrl+E), which edits the record as text.
- **At about 3000 people** each edit rebuilds and rechecks the whole family (about 0.7 s on a laptop); it is usable but not instant.
