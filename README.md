# cronicl

Keep a family tree as plain markdown files in git and generate a static, pan-and-zoom website from them.
GEDCOM is supported as a separate one-way import tool.

Status: v0.1. Design: `docs/superpowers/specs/2026-10-10-cronicl-design.md`.

## Quick start

```bash
uv sync
export CRONICL_DIR=~/my-family            # or pass --dir / -C on every command
uv run cronicl init                       # creates site.yml, people/, archive/
uv run cronicl import-gedcom tree.ged     # preview: counts and warnings
uv run cronicl import-gedcom tree.ged -a  # write the files
uv run cronicl check
uv run cronicl search ashby              # find ids
uv run cronicl edit mark-deceased ashby-greta -a
uv run cronicl serve                      # http://127.0.0.1:8000/
```

## Commands

Every command that works on a cronicl folder takes `--dir DIR` (`-C DIR`), before or after the subcommand.
If it is omitted, `$CRONICL_DIR` is used, and failing that the current directory. Every command that writes
files previews by default and needs `--apply` (`-a`).

| Command | What it does |
|---|---|
| `init` | Create `site.yml` (with a random `id_salt`), `people/`, `archive/`. |
| `check [--format json] [--strict]` | Report problems. Exit 1 on errors (and on warnings with `--strict`). |
| `search WORD... [--limit N] [--format json]` | Fuzzy-find people and print their ids (name, id, years, places; typo- and accent-tolerant). `*` marks people the privacy rules treat as living. Exit 1 when nothing matches. |
| `gaps [--limit N] [--format json]` | List people with missing names, dates, places or parents, best-connected first. |
| `new --given G --surname S [...] [-a]` | Create one person file, with optional dates, places, parents, spouse and children. |
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
- `places/index.html` lists every place named in the files and who was born, died or married there, grouped by
  the last part of the name ("Hamburg, Germany" is under Germany). Nothing is guessed: a region such as
  "Ontario" is its own group unless `site.yml` folds it in (`place_groups: {Ontario: Canada, Holland: Netherlands}`,
  matched ignoring case). A name with no comma that is not a group's own name goes under "Other places".
- `tree/` is the family tree and `timeline/` is the timeline: two pages of one viewer, described next. Every
  address means one thing:

  | Address | Shows |
  |---|---|
  | `tree/` | everyone, fitted to the screen |
  | `tree/#<id>` | the same tree with that person selected |
  | `tree/#focus/<id>` | only that person's line: ancestors and descendants |
  | `timeline/` | the timeline |
  | `timeline/#<id>` | the timeline with that person selected |

  The top bar is the same on every page (Home, Tree, Timeline, People, Places, and a people search). Old
  `tree.html#/...` and `index.html#/...` links are forwarded to these addresses.

The viewer has two modes on the tree page, **Everyone** and **This person's line**, and a find box:

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
  end. Partnerships are small marks on both partners' bars. `timeline/#<id>` selects that person, scrolls to
  their row and dims everyone who is not a parent, partner, child or sibling. People with no dated events are
  listed underneath.
- **Focused tree:** `tree/#focus/<id>`, or "Their line" in the side panel: that person, everyone above them,
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
- **Tree, Overview and zoom:** opening the viewer with no address shows the **Everyone** (`tree/`): everyone, fitted
  to the screen. If you pressed "This is me" on a person page, it opens your own focused tree instead. The
  **Tree** tab shows a focused tree on the selected person (or the home person). A focused tree opens at a
  readable size, and picking a person
  while zoomed far out zooms in on them. Zoom with the buttons at bottom right (**+**, **−**, **Fit**,
  **Home**), the keys `+`, `-` and `0`, the mouse wheel, or a two-finger pinch. Zoomed far out, names give way
  to one label per family ("Smith family · 12"). In a focused tree, a person with relatives that are not drawn
  shows **+N**; double-click a person to focus on them.

Clicking a person opens the side panel; close it with **×**, **Esc**, or by clicking empty canvas (this also
deselects).

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

Only a name is required. `id:` is optional; `cronicl fix` pins it.

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
divorce, annulment or a split. Old `marriages:` entries (with `date:`) still load, and `cronicl fix --apply`
rewrites them as `partnerships:` entries (and bumps `schema_version` to 2).

## Validation

`cronicl check` (also `cronicl validate`) reads everything you edit and reports what it cannot use, with the file,
the key and what to do. It never changes a file. `--format json` gives machine-readable output and `--strict`
makes warnings fail too.

`cronicl build` and `cronicl serve` print errors in full (an error stops the build) but only one line for
warnings, such as `3 warnings: 2 W-UNKNOWN-KEY, 1 W-BAD-LIVING (run cronicl check for details)`. Run `check` for
the list.

What it reports, besides broken references, dates and ids:

| Code | Meaning |
|---|---|
| `W-UNKNOWN-KEY` | a key that nothing reads, at any level of a person file or `site.yml`, with a "did you mean" when it looks like a misspelling (`birht` for `birth`) |
| `W-DUPLICATE-KEY` | the same key twice in one block; the later value wins |
| `W-BAD-LIVING` | a person's `living:` is not `true` or `false`; it is ignored |
| `E-PRIVACY-MODE` | `privacy` is not a mapping, or `privacy.living` is not `full`, `placeholder` or `hidden` |
| `E-PRIVACY-SALT` | `privacy.id_salt` is a list or mapping |
| `W-PRIVACY-NO-SALT` | redaction is on but there is no `id_salt`, so the anonymised ids can be guessed |
| `W-PRIVACY-CUTOFF` | `privacy.cutoff_years` is not a whole number of at least 1; 100 is used |
| `W-SITE-VALUE`, `W-PLACE-GROUPS` | a `site.yml` value of the wrong kind; it is ignored |
| `E-VALIDATOR` | a check failed unexpectedly; the message names the file or step |

**Your own keys.** A key that starts with `x-` or `x_` (any case), such as `x-nickname: Annie`, is yours: it is
kept and never reported. It works at every level. (Inside `gallery:` it only silences the unknown-key warning:
everything there is published to visitors.)

**Values stay text.** `site.yml` is read the way person files are: `NO` is `NO`, `1066` is `1066`, and nothing is
turned into a boolean or a date behind your back. Where a yes/no is expected, write `true`, `yes`, `on`, `1` or
`false`, `no`, `off`, `0` in any case. Where a number is expected, write plain digits.

**Fails closed.** If `site.yml` cannot be read, or `privacy` is broken, a build that you force to continue with
`--ignore-errors` treats living people as `placeholder`, never as public. Fix the error and the real setting applies.
One side effect: anonymised ids come from the exact `id_salt` text. A salt that YAML used to read as a number
(one starting with `0` and made only of digits) now reads as typed, so those ids change once.

## Adding people

The loop that works best once the first import is done:

1. `cronicl gaps` lists who is missing a name, a date, a place or parents, best-connected people first.
2. `cronicl search WORD` finds the ids you need for parents, spouses and children.
3. `cronicl new --given Bob --surname Smith --birth 1950-03-12 --parents smith-john brown-mary` previews a new
   file; add `-a` to write it. Or edit a file in `people/` by hand.
4. `cronicl check` reports anything that does not hold together.
5. `cronicl serve` shows the result.

The table above, "Declare relationships on whichever file you are editing", is the reference for which file to
touch when you add a relative.

## Publishing

Before you publish a site that contains living people, set `privacy.living` to `placeholder` or `hidden` in
`site.yml`. While it is `full`, `build` prints `W-PRIVACY-OFF` with the number of people the privacy rules treat
as living: that is a reminder that they are all published.

`cronicl build --out public` writes a folder of plain files that any static host can serve (see
[Deploying](#deploying) and [Password protection](#password-protection)). Unless you configure a
[photo gallery](#photo-gallery), the site makes no external requests: no web fonts, scripts or analytics are loaded
from anywhere.

`site.yml` keys that shape the published site:

```yaml
title: Hollings family
intro: |                       # Markdown, shown on the home page
  Our family, from Silesia to British Columbia.
home: hollings-nora-doreen     # the person the tree opens on (an id)
edit_url: https://github.com/example/family/edit/main/people/{id}.md   # adds "Edit this page"
contact: mailto:family@example.org    # adds "Suggest a correction" (a mailto: or https:// link)
place_groups:                  # optional: fold a region into its country on the places page
  Ontario: Canada
  British Columbia: Canada
privacy:
  living: placeholder
  cutoff_years: 100
```

`edit_url` must be an `https://` address containing `{id}`; `contact` must be `mailto:`, `http://` or `https://`.
`check` warns about anything else. People hidden or replaced by privacy redaction get neither link.

## Deploying

`cronicl build --out public` writes a folder of plain files: HTML, JSON, JavaScript, CSS and your portraits. Any
static host can serve it, and nothing runs on the server. `cronicl serve` is only for looking at the site while
you edit it; do not use it to publish. Before publishing, set `privacy.living` to `placeholder` or `hidden` in
`site.yml` (see [Publishing](#publishing)).

Every page uses relative addresses, so the site works at the root of a domain or in a subfolder
(`example.com/family/`). Each build clears only the files it generates, so `rsync --delete` of the output
folder is safe. The home page's "recently updated" list reads the data folder's git history, so a build in a
fresh clone needs the full history, not a shallow copy.

### GitHub Pages

Keep your data folder (`people/`, `media/`, `site.yml`) in a GitHub repository. In the repository's *Settings,
Pages*, set *Source* to *GitHub Actions*, then add `.github/workflows/site.yml`:

```yaml
name: Publish site
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # the full history, for "recently updated"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install cronicl    # or however you install cronicl; see the note below
      - run: cronicl build --out public
      - uses: actions/upload-pages-artifact@v4
        with:
          path: public
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Every push to `main` rebuilds and publishes the site. With `edit_url` pointing at the repository (see
[Publishing](#publishing)), a relative can use "Edit this page" on GitHub, and the change goes live by itself.
The action versions above were current when this was written; use the current major versions. The `pip install`
line is the one part that depends on where you keep cronicl: use the package name once it is published, or
`pip install git+https://<where-your-copy-lives>` until then.

**A GitHub Pages site is public, even when its repository is private.** Only organisations on GitHub Enterprise
Cloud can restrict a Pages site to people with access to the repository. Plan accordingly: redact living people,
and see [Password protection](#password-protection) for gated alternatives.

### Your own server

```sh
cronicl build --out out
rsync -a --delete out/ you@yourhost:/var/www/family/
```

Point any web server at that folder. The files are static; there is nothing to configure beyond HTTPS.

### Netlify, Cloudflare Pages, Vercel and similar

Connect the repository, set the build command to `pip install cronicl && cronicl build --out public` and the
publish directory to `public`. These hosts clone with a shallow history by default: turn on a full clone (or
accept that the home page's "recently updated" list is short).

## Password protection

A static site has no logins of its own, so a password has to come from the host or from a service in front of it.
Whatever you choose, keep living people redacted (`privacy.living: placeholder`): a password controls who gets
in, not what they pass on.

| If you have | Use | Notes |
|---|---|---|
| Your own web server | HTTP Basic auth | Simplest and sturdiest; nothing is served before the password is accepted |
| A static host and want real per-person access | Cloudflare Pages plus Cloudflare Access | No shared password; relatives sign in with an emailed code |
| GitHub Pages | See below | Pages cannot require a login on its own |

### Basic auth on your own server

Serve the site over HTTPS only (Basic auth sends the password with every request, so over plain HTTP it is
readable by anyone on the network). Create the password file outside the web root, never in git, with bcrypt:

```sh
htpasswd -B -c /etc/nginx/family.htpasswd family
```

nginx:

```nginx
location / {
    auth_basic "Family";
    auth_basic_user_file /etc/nginx/family.htpasswd;
    add_header X-Robots-Tag "noindex, nofollow" always;
}
```

Apache (`.htaccess`, with `mod_headers`):

```apache
AuthType Basic
AuthName "Family"
AuthUserFile /home/you/.htpasswd-family
Require valid-user
Header set X-Robots-Tag "noindex, nofollow"
```

Use a long passphrase and share it with the family. Consider rate limiting failed logins (fail2ban or your
host's equivalent). The login dialog is the browser's own and there is no logout; for a family site that is
usually acceptable.

### Cloudflare Pages with Cloudflare Access

Cloudflare Pages hosts the static files (connect the repository as above) and Cloudflare Access puts a login in
front of them. In the Cloudflare dashboard, under *Zero Trust*, add a *self-hosted application* covering your
Pages hostname (and any custom domain), with a policy that allows the email addresses of your family and the
*One-time PIN* login method. Each relative then gets a code by email; you can remove one person without changing
a shared password. Cloudflare's free plan covers up to 50 users at the time of writing. Menu names change, so
follow Cloudflare's current documentation for the exact steps.

### GitHub Pages

GitHub Pages itself has no password option (see the note above). Putting Cloudflare in front of it with a
custom domain looks like protection but is not: Pages answers by hostname, so someone who sends requests to
GitHub's servers with your hostname can reach the site without passing Cloudflare. If you need a real gate,
use Cloudflare Pages (above) or your own server instead. If you stay on GitHub Pages, the realistic choices are
a public site with living people redacted, and (weakest) pages encrypted in the browser with a tool such as
StatiCrypt. Encrypted files are still public, so anyone can try passwords against them offline: that is only as
strong as a long passphrase, and this site is many files, not one page.

### Keeping search engines out

None of the above affects search engines on a public site. The `X-Robots-Tag` lines above ask them not to index
a protected site. A public site can add a `robots.txt` that disallows everything and a
`<meta name="robots" content="noindex">` in its pages; cronicl does not generate either yet, and well-behaved
crawlers only.

### A gallery behind a login

The photo gallery (see below) is a separate site with its own protection. A gallery that itself requires a login
is not supported yet: the browser fetches its `people.json` without credentials, so the photos block stays hidden.
A gallery that is public, or protected only by being hard to find, works as described.

## Photo gallery

If you keep your photos in a [Fussel](https://github.com/cbenning/fussel) gallery, cronicl can show a few of a
person's photos on their page, with a link to the rest. Add this to `site.yml`:

```yaml
gallery:
  type: fussel                         # required; fussel is the only type for now
  url: https://example.com/photos/     # the address of the gallery's front page
  label: Family photos                 # optional; the block heading and the top-bar link text (default "Photos")
  portraits: true                      # optional; use the gallery's face as a person's picture (default true)
```

- A person page gets a block of up to six photos, the first one featured, and "See all N photos in the gallery".
  Clicking a photo opens it in a lightbox on the page (arrow keys, swipe and Esc work; "Open in the gallery" links
  to that photo). A link to the gallery is added to the top bar of every page, labelled with `label`.
- If a person has no `portrait:` of their own, the page shows their face from the gallery instead of initials.
  A `portrait:` you set always wins, and `portraits: false` turns this off. It only applies to the person page:
  the build never contacts the gallery, so the tree, people list and timeline keep initials.
- Your browser fetches `people.json` from the gallery when the page opens. If the gallery is down, slow, or has no
  photos of that person, the page looks exactly as it would without a gallery.
- People are found by their name, turned into a lowercase-latin slug (`Zoë Müller` is `zoe-muller`), or, if that
  fails, by the one gallery entry with the same name. If a person is tagged differently in the gallery, put its slug
  in their file: `gallery_id: jane-doe`. Two people with the same name need this too, because Fussel numbers the
  second one. So do names with letters that have no plain-ASCII form (Cyrillic, Chinese, `ð`): Fussel transliterates
  those its own way, so cronicl does not guess and shows no photos for them until `gallery_id` is set.
- People hidden or replaced by privacy redaction never get a photos block.
- It needs a Fussel that writes `people.json` (gallery option `gallery.people.enable: true`, on by default). A
  Fussel that also lists each photo's largest size (`src`) gives sharper featured photos and lightbox; an older one
  still works with the small size.
- A gallery on a different domain can only be read if its host sends an `Access-Control-Allow-Origin` header
  (GitHub Pages does). Without it only the top-bar link works.
- Everything under `gallery:` is published to every visitor, so never put a secret there.

`cronicl check` reports `E-GALLERY-TYPE` (missing or unknown `type`), `E-GALLERY-URL` (missing or not an
`http://` or `https://` address), `W-GALLERY-KEY` (a key that does nothing), `W-GALLERY-PORTRAITS` (`portraits` is
not `true` or `false`), `W-GALLERY-SECRET` (a key named like a secret) and `W-GALLERY-ID-UNUSED` (a `gallery_id` with no usable gallery). An invalid `gallery:` block is ignored
when building.

Another gallery can be added later by registering a type in `galleries.py` and an adapter in `gallery.js`.

## Privacy

**Redaction is off by default.** `cronicl init` writes `privacy.living: full`, and a site with no
`privacy.living` key behaves the same: everyone is published. Turn it on by setting `placeholder` or `hidden`
before you publish a site that contains living people.

When redaction is on, people are treated as living when `living: true`, or when they have no `death` and were
born less than `cutoff_years` ago (default 100); no dates at all also counts as living. Nothing is ever
inferred: `edit mark-deceased` is how you tell cronicl someone is dead. Living people are redacted before any
output file is written, their ids are replaced by salted hashes, and partnership details (type, dates, notes)
involving a living partner are dropped. Mentions of a living person's name inside someone else's biography are not detected.

## Development

```bash
uv sync --extra dev
uv run pytest
```

The suite includes a click-through test that drives a built site in headless Chrome. It is skipped when `node`
or a browser is missing; point `CRONICL_CHROME` at a Chrome/Chromium/`chrome-headless-shell` binary to choose
one.
