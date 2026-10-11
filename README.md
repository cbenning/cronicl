# famsite

Keep a family tree as plain markdown files in git and generate a static, pan-and-zoom website from them.
GEDCOM is supported as a separate one-way import tool.

Status: v0.1. Design: `docs/superpowers/specs/2026-10-10-famsite-design.md`.

## Quick start

```bash
uv sync
uv run famsite init my-family            # creates site.yml, people/, archive/
uv run famsite import-gedcom tree.ged --into my-family            # dry run
uv run famsite import-gedcom tree.ged --into my-family --apply    # write files
uv run famsite check my-family
uv run famsite build my-family --out my-family/out
uv run famsite serve my-family            # http://127.0.0.1:8000/
```

## Commands

| Command | What it does |
|---|---|
| `init [DIR]` | Create `site.yml` (with a random `id_salt`), `people/`, `archive/`. |
| `check [DIR] [--format json] [--strict]` | Report problems. Exit 1 on errors (and on warnings with `--strict`). |
| `fix [DIR] [--apply] [--force]` | Rename files to match ids, pin missing ids, normalise formatting, resolve filename collisions, rewrite references. Dry run unless `--apply`; refuses a dirty git tree unless `--force`. |
| `import-gedcom FILE [--into DIR] [--apply]` | One-time GEDCOM import; archives the original file. |
| `build [DIR] [--out DIR] [--force]` | Run `check`, then generate the static site. |
| `serve [DIR] [--port N]` | Build and serve locally. |
| `schema` | Print a JSON Schema for the frontmatter (for agents and editors). |

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

People are treated as living when `living: true`, or when they have no `death` and were born less than
`cutoff_years` ago (default 100); no dates at all also counts as living. `site.yml` `privacy.living` is one of
`hidden`, `placeholder` (default) or `full`. Living people are redacted before any output file is written, their
ids are replaced by salted hashes, and marriage details involving a living spouse are dropped. Mentions of a
living person's name inside someone else's biography are not detected.

## Development

```bash
uv sync --extra dev
uv run pytest
```
