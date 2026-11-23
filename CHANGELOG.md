# Changelog

## 1.4.0

- New: in the terminal app, "Add a child" keeps the picker open so you can pick several children in a row (Esc when
  done), and "Add a parent" lets you pick both parents before it closes.

## 1.3.0

- The terminal editor's person list and person picker show each person's parents (`↑ Tom & Anne`) and first children
  (`↓ Sam, Pat +1`) as the terminal allows, so people who share a name can be told apart. A parent or child with a
  different surname from the person shows it.

## 1.2.0

- New: `cronicl --version` prints the installed version.

## 1.1.0

- Fix: the GEDCOM export header named cronicl version 0.1.0 whatever the installed version; it now names the real one.
- Python 3.10 is no longer supported: it reached end of life in October 2026. cronicl needs Python 3.11 or newer.
  Tests run on the oldest (3.11) and the newest (3.15) supported versions.
- New: `adoptive-parents` on a person, a list of at most two ids beside `parents` (birth parents). Either may be
  left out, so a person whose birth parents are unknown needs only `adoptive-parents`, and an `adoption` event needs
  no date. The tree, relatives and descendants use the adoptive parents when there are any; `show` and the terminal
  editor list both kinds. `cronicl new` takes `--adoptive-parents`, and `rename` follows the ids.
- GEDCOM: `FAMC` with `PEDI adopted` now imports as `adoptive-parents` (it was set aside), `ADOP` imports as an
  `adoption` event, and export writes both family links with `PEDI`, plus `ADOP`. A person with a birth family and an
  adoptive family no longer gets a `W-CHIL-CONFLICT` warning.
- The site draws an adopted child's line to the adoptive couple dotted. A person's page shows "Birth parents" when
  they are known, marks adoptive parents and adopted children, and a birth parent's page lists "Children raised by
  others".
- GEDCOM import no longer links a `PEDI foster` or `PEDI sealing` family as the person's birth parents; it warns
  (`W-PEDI-UNMAPPED`) and keeps the lines. `ADOP HUSB` and `ADOP WIFE` limit `adoptive-parents` to that one parent.
- New check `W-TOO-MANY-ADOPTIVE-PARENTS`. Date checks (`W-CHILD-BEFORE-PARENT`, `W-CHILD-AFTER-PARENT-DEATH`) look
  at birth parents only.

## 1.0.1

- Fix: a photo gallery served from the same address as the site, behind one login such as HTTP Basic auth, now shows
  its photos block. The browser sends its login with the gallery request when the gallery is on the site's own
  origin; a gallery on another address is still fetched without credentials. The README section "A gallery behind a
  login" describes the setup.
- Updated the locked Python dependencies and the GitHub Actions used by the workflows.

## 1.0.0

The first release of cronicl as a family-tree tool. (Version 0.1.0 on PyPI was an unrelated project that used the
name before; it is yanked, and this release follows it.)

- A family tree kept as plain YAML in one `family.yml` (or a `family/` folder), with a written format
  ([`SPEC.md`](SPEC.md)), a JSON Schema and a conformance suite.
- `cronicl check` validates the tree with the file and line of every problem.
- A full-screen terminal editor (run `cronicl` with no command) that shows a diff before it writes.
- GEDCOM import and GEDCOM 5.5.1 export.
- A static site generator: a pan-and-zoom tree, a person's line, a timeline, person pages, places, kinship, sources
  and an optional map. Living people can be shown, masked or hidden.
