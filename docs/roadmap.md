# Roadmap: work not yet built

One document for everything still open, so a session can pick portions of it. Items are numbered and independent
unless a "Needs" line says otherwise. Pick by number, for example "do 1.3 and 1.5".

Built and merged (not listed here): the family file (specified in `SPEC.md`), validation, gallery, GEDCOM import
and export, citations, the map, and the noindex output.
Small known defects are in `docs/known-issues.md`.

## Contents

1. Polish batch (design in full below)
   - 1.1 `cronicl serve` watches files and reloads the browser
   - 1.2 `check` place hygiene (`W-PLACE-EMPTY-PART`, `W-PLACE-NO-COMMA`, `W-PLACE-VARIANT`)
   - 1.3 Descendants count: count distinct people
   - 1.4 Malformed link hash must not throw
   - 1.5 `W-HOME-REDACTED` for a `home:` person who will be redacted
   - 1.6 Non-Latin surnames grouped on the People page
   - 1.7 Timeline pans to the selected person's bar
3. Deploy docs: GitHub Pages public-repo warning; Cloudflare Pages recipe
4. Gallery fetch: send `credentials: 'same-origin'` on the gallery request
5. Map and citation follow-ups
   - 5.1 Show couple-event (marriage) citations on the site; today they are kept and exported but not shown
   - 5.2 Fractional map zoom and a date-line-aware initial fit
6. Family-file review leftovers (see section 6)
7. README full rewrite (do last, after 2 and 1 are settled)

## 1. Polish batch

Design written before the family file and updated for it and the cronicl name. Checked against the code on 2026-11-15: nothing in it is built yet,
and fixes 1 to 4 still reproduce. Fix 5 (1.7) is unconfirmed; write its failing test first. Notes added since the
design was written:

- When 1.2 compares place strings it should use the same normalisation as the map (`norm_place` in
  `src/cronicl/site/mapdata.py`) instead of adding a third one. The map has its own codes (`W-PLACE-COORDS`,
  `W-PLACE-UNKNOWN`); the place-hygiene codes below do not replace them.
- Numbering: the original design's part 1 is 1.1, part 2 is 1.2, and its five fixes are 1.3 to 1.7 in the order listed.
- Build order: nothing here depends on the other items. 1.1 is the largest.

#### Intent

Make day-to-day use of cronicl smoother and its output more trustworthy. Three parts, all small, all
local-only (no new dependencies, no network):

1. `cronicl serve` rebuilds and reloads the browser when the owner saves a file, so editing a record and
   seeing the result no longer means stopping and restarting the server.
2. `cronicl check` points out place names that will group badly or probably mean the same place spelled two ways.
3. Five known defects that show wrong or broken output to visitors or authors are fixed.

Out of scope here (later batches): share-preview tags, a printable pedigree, hosting recipe, access gate.

#### Goals

- Saving `family.yml` (or a file in `family/`), `site.yml` or a file under `media/` while `cronicl serve` runs updates the browser
  within about two seconds, with no manual step.
- A build that fails while serving (for example a broken `site.yml`) leaves the last good site up and says
  what is wrong, in the terminal and in the browser. Fixing the file recovers by itself.
- `check` names the specific place strings and people behind a place problem, with the `family.yml` line, so the owner can fix the file.
- Each of the five fixes is pinned by a test that failed before it.

#### Non-goals and anti-goals

- No file-watching dependency (poll file modification times). No WebSocket. No hot module replacement.
- No change to anything the built site contains: the reload script and state endpoint exist only in the `serve`
  process. A site built with `cronicl build` is byte-identical to today's apart from the five fixes.
- `check` place findings are warnings, never errors, and never change `build` results.
- No fuzzy guessing that edits data. Place checks only report.
- Anti-goal: a serve loop that rebuilds in a tight cycle, rebuilds twice for one save, or hangs the browser.

#### 1.1 `cronicl serve` watches by default

- Watching is on by default; `--no-watch` gives today's behaviour (build once, serve). `serve` is a development
  command, so the default favours the person editing.
- Watched: `site.yml`; `family.yml`, or every `*.yml` directly in `family/` (the same files the loader reads, not
  subfolders); and every file under `media/` (recursively). A change is any
  file added, removed, or whose modification time or size changed.
- A poll runs about every 0.5 s. A change triggers a rebuild only once two consecutive polls agree on the new
  state (so a save that touches a file twice, or a multi-file save, rebuilds once, after it settles).
- A rebuild runs the same code path as `cronicl build` (check, then build into the same `--out` folder), with the
  same `--ignore-errors` setting `serve` was started with. The shared code returns its result (success, the
  messages `build` would print, the summary) instead of only printing, so `build` and `serve` both use it.
  A rebuild fails when `build` would exit non-zero (error-level check issues without `--ignore-errors`, the
  `--out would overwrite the data folder` refusal) or when building raises an exception. The previous output
  stays in place and the failure text (the error messages, or the exception message) is kept as the current error.
- **First build fails.** `serve` still starts (with `--no-watch` it keeps today's behaviour: print the error, exit
  non-zero). It serves whatever is already in the `--out` folder if that holds an `index.html` (a stale build from
  an earlier run, shown with the error banner), otherwise a minimal built-in page that says the first build
  failed and shows the error. `/__cronicl/state` reports `build: 0` and the error until a build succeeds; the
  page reloads itself when it does.
- The serve process exposes `GET /__cronicl/state` returning `{"build": <int>, "error": <string or null>}` with
  `Cache-Control: no-store`. `build` increases by one after every successful rebuild (it is 1 after the first).
- HTML responses served by `serve` (and only those) get a small script inserted before `</body>`. It polls
  `/__cronicl/state` once a second; when `build` changed it reloads the page (scroll position and URL hash are
  kept by the browser); when `error` is set it shows a fixed, dismissible banner with the text (set with
  `textContent`), and hides it when the error clears. The script makes no other request and fails quietly if
  the endpoint is unreachable (for example when the page is opened from another server).
- The terminal prints, once per rebuild, exactly what `cronicl build` prints (warnings, then the `built N people,
  M files into OUT` line) or the failure text. Nothing is printed while idle.
- Ctrl+C stops everything promptly.
- While a rebuild is writing, a request may briefly see a half-written site; the reload happens only after the
  rebuild finishes, so the owner sees the finished result.

#### 1.2 `cronicl check`: place hygiene

Warnings (code, when, message must name the place string and up to three person ids that use it):

| Code | When |
|---|---|
| `W-PLACE-EMPTY-PART` | a place has an empty part between commas (`Sooke, , British Columbia`) |
| `W-PLACE-NO-COMMA` | a one-part place that the places page would list under "Other places" (it is not a country-style group name, taking `site.yml` `place_groups` into account) |
| `W-PLACE-VARIANT` | two different place strings that are probably the same place: they are equal after folding case, accents, punctuation and spacing, or they share the same last part and are at least 92 % similar (`difflib.SequenceMatcher` ratio, both at least 6 characters), e.g. `Heidelburg, Germany` and `Heidelberg, Germany`. One warning per pair, naming both strings. |

Each warning names the place string (both strings for a variant) and up to three records that use it, as
`family.yml:214` style locations (the issue's own line is the first use). A place in a couple's events names the
couple (`a + b`). The rules live in `cronicl.core` next to the other family rules, because they are about the
file; the places page's grouping rule is shared by both, not copied. `W-PLACE-EMPTY-PART` is rare now that
`W-FLOW-COMMA` catches the unquoted-comma trap, but a doubled comma inside quotes still gets through.

Place strings come from the same sources as the places page (`birth` and `death` places and `events` places, for people and for couples). Nothing is
changed or suggested beyond naming the pair. Comparisons are within the same last part, so cost stays small.

#### 1.3 to 1.7 The five fixes

1.3 **"Descendants (N)" counts people twice.** A person reachable through two lines (a descendant who appears
   under both parents' branches, cousins marrying) is listed under each line but counted once in N.
   Count distinct person ids. The listing itself is unchanged.
1.4 **A malformed link hash throws.** `tree/#%E0%A4%A` (invalid percent-encoding) makes the viewer's route parser
   throw `URIError` and the page does not start. Decode each part safely; a part that cannot be decoded is kept
   as written, so the page opens as an unknown person (the tree's normal "not found" behaviour).
1.5 **`home:` naming a person who will be redacted is silently ignored.** With `privacy.living` set to
   `placeholder` or `hidden`, a configured home person who counts as living is not in the published tree, so the
   home setting is ignored with no explanation. `check` adds `W-HOME-REDACTED` on the `home:` line of `site.yml` (message: the person is treated
   as living and hidden, so the home setting is ignored). Behaviour is unchanged otherwise. Uses the same
   living rule as the build (`cronicl.core.living.is_living`: `living: true`, `death`, `death: unknown`, the
   latest-year rule for qualified birth dates) and `privacy.cutoff_years`; `check_tree` gains an optional `today: date | None = None`
   (default today) for testing.
1.6 **Non-Latin surnames all collapse into "No surname recorded" on the People page.** `slugify` drops them. Group
   such people by their surname folded with Unicode NFC and `casefold()`; the heading is the surname as written;
   the group's anchor id is `s-` plus the first 8 hex characters of the SHA-1 of the folded surname. Order: Latin
   groups (by slug) first, then non-Latin groups (by folded surname), then "No surname recorded". Existing
   Latin anchors and order do not change.
1.7 **Selecting a person on the timeline does not bring their bar into view horizontally.** Opening
   `timeline/#<id>` when the current time window (zoom) does not cover that person's life scrolls vertically to
   their row but leaves the window where it was, so the row looks empty. Pan the window (keep the zoom) so the
   person's lifespan is visible: centre it if it fits, otherwise align its start with the window's left edge.
   If the window already shows any part of the lifespan, leave it alone.

#### Constraints

- Python stdlib only for watching, similarity and hashing. Existing dependency set unchanged.
- ES5-style JS in `viewer.js` as today; the injected reload script is a short inline ES5 snippet.
- All checks are deterministic and fast (a 5 000-person site's place check completes in well under a second).

#### Left to the builder

Names of functions and files, how the watcher is structured and tested (inject the poll interval so tests
finish quickly), the exact banner markup and style, how the timeline code expresses the pan, and whether to
extract the build step from `cmd_build` into a function both `build` and `serve` call.

## 3. Deploy docs

Add to the README's hosting section: a warning that GitHub Pages on a free account needs a public repository, so the
family data would be public, and a Cloudflare Pages recipe. Fold into item 7 if the README is rewritten first.

## 4. Gallery fetch credentials

The gallery's browser request should be sent with `credentials: 'same-origin'`. Files: `src/cronicl/site/viewer/gallery.js`
and `tests/js/` (add a unit that pins the option). Related config: `src/cronicl/site/galleries.py`.

## 5. Map and citation follow-ups

- 5.1 Citations on couple events are kept in `family.yml` and written to GEDCOM export, but the site shows none on
  couple events. Show them as footnotes on both partners' pages, using `annotate()` in `src/cronicl/site/sources.py`.
- 5.2 The map uses integer zoom and an initial fit that ignores the date line. Only matters for families spread
  across the Pacific. Code: `fit` in `src/cronicl/site/viewer/map.js`.

## 6. Family-file review leftovers

Minor findings from the family-file review that were deferred. Each needs its own failing test first.

- Unquoted legacy extra keys are not quoted on emit.
- `NEL` is not quoted on emit.
- Renaming a person with anchors does not update the anchors.
- `mark-deceased` on a blank death.
- Loader speed on large files.
- GEDCOM import of a bare `DEAT` or `ENGA`.
- Wrong-shaped values are not always reported.
- Some issues have no line number.
- `family/` folder quirks.
- Some validation codes are undocumented.
- Stale strings and dead code.
- Test gaps.

These are one-line notes from the review; the details are in git history for the family-file branch and in the
session notes, and should be re-derived before fixing.

## 7. README full rewrite

The README has grown section by section and has no single shape. Rewrite it once as one document, after the
distribution name (item 2) and the polish batch (item 1) are settled. Until then keep README edits to the minimum a
feature needs.
