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

`serve` / `build` produce a single-page site with tabs:

- **Tree:** every person on a pan-and-zoom canvas (only what is on screen is drawn). Long names wrap onto two
  lines; siblings and half-siblings always share a row.
- **Timeline:** every dated birth, marriage and death on one horizontal, zoomable time axis. People with no
  dated events are listed underneath.
- **Person timeline:** `#/timeline/<id>`, or "Their timeline" in the side panel: that person's own events plus
  their relatives' (parents' deaths, spouses' deaths, children's and siblings' births and deaths), with ages.

Clicking a person opens the side panel; close it with **×**, **Esc**, or by clicking empty canvas (this also
deselects). URLs are `#/tree[/<id>]` and `#/timeline[/<id>]`.

## Data layout

```
site.yml            title, schema_version, privacy settings
people/<id>.md      one file per person -- the only record type
archive/            original .ged files, unmodified
```

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
marriages:
  - with: jones-jane
    date: 1975-06-20
    place: Surrey, BC
---
Free-form biography in markdown.
```

Only a name is required. `id:` is optional; `famsite fix` pins it.

### Declare relationships on whichever file you are editing

| Add | Write |
|---|---|
| A child of a known couple | one new file with `parents: [a, b]` |
| A spouse | one new file with `spouse: [a]` (or a `marriages` entry) |
| A parent of an existing person | one new file with `children: [existing-id]`; no existing file changes |

`parents` is the canonical up-reference. `children`, `spouse` and `marriages` may be declared on either
end and are merged. Couples are derived; there are no couple files.

## Privacy

**Redaction is off by default.** `famsite init` writes `privacy.living: full`, and a site with no
`privacy.living` key behaves the same: everyone is published. Turn it on by setting `placeholder` or `hidden`
before you publish a site that contains living people.

When redaction is on, people are treated as living when `living: true`, or when they have no `death` and were
born less than `cutoff_years` ago (default 100); no dates at all also counts as living. Nothing is ever
inferred: `edit mark-deceased` is how you tell famsite someone is dead. Living people are redacted before any
output file is written, their ids are replaced by salted hashes, and marriage details involving a living
spouse are dropped. Mentions of a living person's name inside someone else's biography are not detected.

## Development

```bash
uv sync --extra dev
uv run pytest
```

The suite includes a click-through test that drives a built site in headless Chrome. It is skipped when `node`
or a browser is missing; point `FAMSITE_CHROME` at a Chrome/Chromium/`chrome-headless-shell` binary to choose
one.
