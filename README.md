# famsite

Keep a family tree as plain markdown files in git and generate a static, pan-and-zoom website from them.
GEDCOM is supported as a separate one-way import tool.

Status: v0.1. Design: `docs/superpowers/specs/2026-10-10-famsite-design.md`.

## Quick start

```bash
uv sync
export FAMSITE_DIR=~/my-family            # or pass --dir / -C on every command
uv run famsite init                       # creates site.yml, people/, archive/
uv run famsite import-gedcom tree.ged     # preview: counts and warnings
uv run famsite import-gedcom tree.ged -a  # write the files
uv run famsite check
uv run famsite search ashby              # find ids
uv run famsite edit mark-deceased ashby-greta -a
uv run famsite serve                      # http://127.0.0.1:8000/
```

## Commands

Every command that works on a famsite folder takes `--dir DIR` (`-C DIR`), before or after the subcommand.
If it is omitted, `$FAMSITE_DIR` is used, and failing that the current directory. Every command that writes
files previews by default and needs `--apply` (`-a`).

| Command | What it does |
|---|---|
| `init` | Create `site.yml` (with a random `id_salt`), `people/`, `archive/`. |
| `check [--format json] [--strict]` | Report problems. Exit 1 on errors (and on warnings with `--strict`). |
| `search WORD... [--limit N] [--format json]` | Fuzzy-find people and print their ids (name, id, years, places; typo- and accent-tolerant). `*` marks people the privacy rules treat as living. Exit 1 when nothing matches. |
| `gaps [--limit N] [--format json]` | List people with missing names, dates, places or parents, best-connected first. |
| `fix [-a] [--allow-dirty]` | Rename files to match ids, pin missing ids, normalise formatting, resolve filename collisions, rewrite references. Refuses a dirty git tree unless `--allow-dirty`. |
| `import-gedcom FILE [-a]` | One-time GEDCOM import; archives the original file. |
| `edit mark-deceased ID... [-a]` | Write `living: false` for the named people. Targeted text edit; all ids are validated first. |
| `edit mark-living ID... [-a]` | Write `living: true` for the named people. |
| `build [--out OUT] [--ignore-errors]` | Run `check`, then generate the static site (default `OUT` is `<dir>/out`). |
| `serve [--out OUT] [--port N] [--ignore-errors]` | Build and serve locally. |
| `schema` | Print a JSON Schema for the frontmatter (for agents and editors). Needs no folder. |

`edit` holds every command that changes a person file by hand-picked id, so it stays separate from the
read-only utilities. There is deliberately no bulk form.

## Views

`serve` / `build` produce a static site:

- `index.html` is the **home page**: a heading and optional `intro:` text (Markdown, from `site.yml`), a
  search box, the home person, the numbers (people, generations, years), the commonest surnames, an
  "On this day" list (filled in by the browser) and recently updated people (from the data folder's git history,
  when it is a repository).
- `people/index.html` lists everyone grouped by surname; any page's search box filters it (`?q=`).
- **Kinship:** each person page and side panel says how that person is related to you ("Your
  great-grandmother"). Press **This is me** on your own page and the choice is remembered in your browser only
  (`localStorage`, never sent anywhere); until then relations are told from the home person's side.
  `relate/index.html` answers "how are these two people related?" for any pair (`?a=<id>&b=<id>`). Kinship is
  worked out in the browser from `kin.json`; pages without JavaScript simply omit the line.
- `places/index.html` lists every place named in the files and who was born, died or married there.
- `tree.html` is the viewer, described next; old `index.html#/...` links are forwarded to it.

The viewer has tabs:

- **Tree:** every person on a pan-and-zoom canvas (only what is on screen is drawn). Long names wrap onto two
  lines; siblings and half-siblings always share a row.
- **Reading the tree:** at rest every connector and box outline is one quiet, light colour, and hovering a
  person only accents that one box. Selecting a person shades their own line by generation: oldest ancestors
  deep red, the selected generation violet, the youngest descendants green, with partners dashed and everyone
  off the line faded. Each side of the ramp is stretched over its own depth, and hovering a node says how many
  generations it is above or below. A **Family** toggle in the legend (remembered in the browser) switches to
  relationship colours instead: parents orange, partners pink, children green, siblings (including
  half-siblings) violet.
- **Islands:** families that are not connected to each other are laid out as separate blocks, largest first, left
  to right, so a small unrelated family can no longer sit in the middle of the main tree and bend its lines.
  People with no recorded relatives go in a labelled "Not connected to anyone" grid below everything else.
- **Timeline:** one lifespan bar per person on a zoomable time axis that never runs past next year. A living
  person's bar runs to today; a bar with no recorded death fades out after eight years rather than guessing an
  end. Partnerships are small marks on both partners' bars. `#/timeline/<id>` selects that person, scrolls to
  their row and dims everyone who is not a parent, partner, child or sibling. People with no dated events are
  listed underneath.
- **Focused tree:** `#/focus/<id>`, or "Focus tree" in the side panel: that person, everyone above them,
  everyone below them, and the spouses of those people. Siblings, aunts and uncles are hidden until you pick
  "Show full tree". The layouts are generated by `build` (`focus/<id>.json`), so there is nothing extra to run.
- **Person page:** `p/<id>/` is a static, printable page per person, written as a short biography: name, year
  label ("1941–2021", or "b. 1907" when only a birth is known), a sentence of life facts ("Born 12 March 1941
  in Guelph. Died 2021, aged 80."), the biography as prose, one Family block (parents, partners, children,
  and siblings as a compact row), one dated timeline with ages (relatives' events muted), and collapsible
  Ancestors (four generations) and Descendants lists. Empty parts are left out. The side panel shows the same
  life sentence and relatives. Warm neutral colours, serif names and headings, and automatic dark mode are used
  throughout; no web fonts are loaded.
- **Ended partnerships:** a couple whose partnership has an `end` is drawn with dashed spouse lines and a
  hollow dot; the side panel shows "Married 1975 – divorced 1990".
- **Tree, Overview and zoom:** the **Tree** tab opens a focused tree on the home person (or the selected
  person); **Overview** (`#/tree`) draws everyone. The tree opens at a readable size, and picking a person
  while zoomed far out zooms in on them. Zoom with the buttons at bottom right (**+**, **−**, **Fit**,
  **Home**), the keys `+`, `-` and `0`, the mouse wheel, or a two-finger pinch. Zoomed far out, names give way
  to one label per family ("Smith family · 12"). In a focused tree, a person with relatives that are not drawn
  shows **+N**; double-click a person to focus on them.

Clicking a person opens the side panel; close it with **×**, **Esc**, or by clicking empty canvas (this also
deselects). URLs are `#/tree[/<id>]`, `#/focus/<id>` and `#/timeline[/<id>]`.

## Data layout

```
site.yml            title, intro, home, schema_version, privacy settings
people/<id>.md      one file per person -- the only record type
archive/            original .ged files, unmodified
media/              portrait images named by `portrait:` in a person file
```

`home:` in `site.yml` names the person the tree opens on (a person id). Without it the person with the most
descendants is used; `check` warns when `home:` names nobody.

`portrait: scans/nora.jpg` names one picture for a person, as a path under `media/` (`.jpg`, `.jpeg`, `.png`,
`.webp`, `.gif`, `.avif`). `build` copies each referenced file, unchanged, to `out/media/`; nothing is resized,
so keep portraits at most 600px wide and under 1 MB (`check` warns above 1 MB). The picture shows on the person
page, in the side panel and on the person's tree box. A path that leaves `media/` is an error and is never
copied, and a person hidden or replaced by privacy redaction never has a portrait.

A person file:

```markdown
---
id: smith-bob
name:
  given: Bob
  surname: Smith
birth:
  date: 1950-03-12
  place: Vancouver, BC
parents: [smith-john, brown-mary]
partnerships:
  - with: jones-jane
    type: marriage          # marriage | civil-union | partnership | engagement | unknown
    start: 1975-06-20
    end: 1990-02-01         # a date, or `unknown`; leave out while it is ongoing
    end_reason: divorce     # divorce | annulment | separation
    place: Surrey, BC       # where it began
events:                     # anything beyond birth and death
  - type: occupation
    value: Teacher
    cite: Census 1911       # one source, or a list
  - type: immigration
    date: 1952-04
    place: Halifax, NS
    note: Aboard the Arosa Kulm
---
Free-form biography in markdown.
```

Only a name is required. `id:` is optional; `famsite fix` pins it.

### Events, notes and sources

`events:` is a list of things that happened to a person or are true of them. `type` is any slug you like
(hyphens read as spaces); each entry may have `date` (or `start` and `end` for a span), `place`, `value` (for
attributes such as an occupation), `note` and `cite`. Entries with a date appear on the person's page,
in the side panel and as ticks on their bar in the timeline; entries without a date are listed as facts.
`birth` and `death` may carry `note` and `cite` too. Known types read as words (`burial` is "buried",
`immigration` "immigrated", `residence` "lived", `occupation` with a value "worked as Teacher", and so on);
others are shown as written. People treated as living under redaction never have events, notes or sources
published. `import-gedcom` maps individual events and attributes (BAPM, CHR, CONF, BURI, CREM, IMMI, EMIG, NATU,
RESI, OCCU, EDUC, RELI, NATI, GRAD, RETI, CENS, WILL, PROB) to `events:`; a line whose date cannot be converted,
and anything else it does not know, stays in `gedcom_extra`. Imports made before this version keep those lines in
`gedcom_extra` until you type them in by hand. Search also finds event places and values.

### Declare relationships on whichever file you are editing

| Add | Write |
|---|---|
| A child of a known couple | one new file with `parents: [a, b]` |
| A spouse | one new file with `spouse: [a]` (or a `partnerships` entry) |
| A parent of an existing person | one new file with `children: [existing-id]`; no existing file changes |

`parents` is the canonical up-reference. `children`, `spouse` and `partnerships` may be declared on either
end and are merged: `start` on one file and `end` on the other make one partnership. Couples are derived;
there are no couple files. A partner's death never sets `end`, and nothing is inferred; `end` is only for
divorce, annulment or a split. Old `marriages:` entries (with `date:`) still load, and `famsite fix --apply`
rewrites them as `partnerships:` entries (and bumps `schema_version` to 2).

## Privacy

**Redaction is off by default.** `famsite init` writes `privacy.living: full`, and a site with no
`privacy.living` key behaves the same: everyone is published. Turn it on by setting `placeholder` or `hidden`
before you publish a site that contains living people.

When redaction is on, people are treated as living when `living: true`, or when they have no `death` and were
born less than `cutoff_years` ago (default 100); no dates at all also counts as living. Nothing is ever
inferred: `edit mark-deceased` is how you tell famsite someone is dead. Living people are redacted before any
output file is written, their ids are replaced by salted hashes, and partnership details (type, dates, notes)
involving a living partner are dropped. Mentions of a living person's name inside someone else's biography are not detected.

## Development

```bash
uv sync --extra dev
uv run pytest
```

The suite includes a click-through test that drives a built site in headless Chrome. It is skipped when `node`
or a browser is missing; point `FAMSITE_CHROME` at a Chrome/Chromium/`chrome-headless-shell` binary to choose
one.
