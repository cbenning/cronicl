# The family file format

This document specifies `family.yml`, the file in which a cronicl family tree is kept. It is written for people who
edit the file and for anyone writing another tool that reads or writes it. cronicl is one implementation; a
conformance suite (`tests/conformance/`) and a JSON Schema (`cronicl schema`) travel with the specification, so
another implementation can check itself against them.

The key words MUST, SHOULD and MAY are used as in RFC 2119.

## 1. Goals

- A person who knows a text editor can maintain a whole family in one file: find anyone with a text search, add a
  branch by typing a few short blocks, rename someone with one find-and-replace.
- Every fact has one place and one shape. Nothing that can be derived is written.
- Mistakes are found by a checker that names the file and the line.
- GEDCOM maps onto the format cleanly in both directions.
- A tool that edits one record leaves every other byte of the file alone: comments, blank lines, record order and
  formatting belong to the owner.

## 2. The data folder

```
site.yml        settings for the generated site (schema_version: 3)
family.yml      every person and couple
media/          portraits, named by `portrait:`
archive/        original .ged files; material set aside by import
```

When one file becomes unwieldy the owner MAY instead keep a folder `family/` of `.yml` files in the same format,
split however they like. Having both `family.yml` and `family/` is an error. All files are read as one stream, and
a record's id MUST be unique across them. Only the `.yml` files directly in `family/` are read.

## 3. Reading the file

`family.yml` is YAML. A reader MUST:

- read every scalar as text exactly as typed: `NO` is the text `NO`, `1066` is the text `1066`, `2020-01-01` is
  text, not a date (YAML's "failsafe" schema);
- report a key that occurs twice in one mapping (the later value wins);
- reject merge keys (`<<`).

Two things trip people up when typing YAML:

- Inside `{...}` or `[...]` a comma separates entries, so text that contains a comma MUST be quoted there:
  `place: "London, England"`. On a line of its own (`place: London, England`) no quotes are needed.
- Text containing `: ` (colon, space) or beginning with `#`, `*`, `&`, `!`, `[` or `{` needs quotes.

The order of records, blank lines and `#` comments carry no meaning.

## 4. Records

The top level is a mapping, and every key is a record. Two kinds are told apart by the key:

- **A person:** the key is the person's id (`lovelace-ada`).
- **A couple:** the key is two different person ids joined by a plus sign (`byron-george + milbanke-annabella`).
  Spaces around the plus are optional and either order is accepted. `a + b` and `b + a` are the same couple, and
  writing both is a duplicate.

```yaml
byron-george:
  name: {given: George, surname: Byron}
  birth: {date: 1788-01-22, place: "London, England"}
  death: {date: 1824-04-19, place: "Missolonghi, Greece"}

milbanke-annabella:
  name: {given: Annabella, surname: Milbanke}
  birth: 1792-05-17

byron-george + milbanke-annabella:
  events:
    - {type: marriage, date: 1815-01-02, place: "Seaham, England"}
    - {type: separation, date: 1816}

lovelace-ada:
  name: {given: Augusta Ada, surname: Lovelace}
  sex: female
  birth:
    date: 1815-12-10
    place: London, England
    note: Born at Piccadilly Terrace.
    cite: Parish register, St George Hanover Square
  death: {date: 1852-11-27, place: "London, England"}
  parents: [byron-george, milbanke-annabella]
  events:
    - {type: occupation, value: Mathematician, cite: Letters to Charles Babbage}
    - {type: residence, date: FROM 1835 TO 1852, place: "Ockham Park, Surrey"}
    - {type: burial, date: 1852-12-03, place: "Hucknall, Nottinghamshire"}
  portrait: ada.png
  refs: {gedcom: "@I123@", gallery: ada-lovelace}
  x-nickname: Enchantress of Number
  bio: |
    Mathematician and writer, known for her notes on Babbage's Analytical Engine.
```

### 4.1 Principles

1. **One fact, one place.** A fact about one person is in that person's record. A fact about two people as a couple
   is in the couple's record. Nothing is stored twice, so nothing can disagree.
2. **Links point up.** Parentage is a fact about the child: `parents:` is on the child. Children, siblings,
   partners and descendants are never written; a reader derives them.
3. **Once-only things are fields; repeatable things are a list.** A person is born once and dies once, so `birth`
   and `death` are fields. Everything else, for a person or a couple, is an entry in `events:`. That includes
   marriage: the same two people can marry, divorce and marry again.
4. **One shape for a dated fact**, used by `birth`, `death` and every event.
5. **The id is the key.** There is no `id:` field and no file name to keep in step.
6. **Nothing is guessed.** A reader MUST NOT infer anything from names, dates or position in the file, and MUST
   report a conflict instead of resolving it quietly.

### 4.2 Ids

A person id matches `^[a-z0-9]+(-[a-z0-9]+)*$` and is at most 64 characters. By convention it is surname first
(`lovelace-ada`, `smith-john-1850`), so a text search for a surname finds the family. Ids appear in page
addresses, so changing one changes links.

### 4.3 A dated fact

A dated fact is a mapping with any of:

| Key | Meaning |
|---|---|
| `date` | when (see section 5) |
| `place` | where, as text (`Ockham, Surrey`); the last comma-separated part is the country or region used for grouping |
| `note` | a remark shown with the fact |
| `cite` | where the fact comes from: one text, or a list of texts. Plain text, never markup |

For `birth` and `death`, when the date is all there is, the date alone is enough: `birth: 1820` means
`birth: {date: 1820}`. A date of `unknown` means "it happened, the date is not known": `death: unknown` marks a
person as dead without a date. A fact left blank (`death:` with nothing after it) is ignored and reported.

### 4.4 A person record

| Key | Shape | Notes |
|---|---|---|
| `name` | mapping | `given`, `surname`; optional `prefix`, `suffix`, `nickname`, and `also` (a list of other names, such as a married name). The displayed name is prefix, given, surname, suffix |
| `sex` | `male`, `female`, `unknown`, `other` | absent means unknown |
| `birth`, `death` | dated fact | a person with `death` is deceased |
| `parents` | list of at most two person ids | birth parents |
| `events` | list of mappings | see 4.6 |
| `portrait` | text | a path under `media/` |
| `living` | `true` | only to say someone is alive when their dates suggest otherwise. To say someone is dead, use `death` |
| `refs` | mapping | ids in other systems: `gedcom` (the record's id in an imported file), `gallery` (the person's id in a photo gallery) |
| `bio` | text | the biography, as markdown |
| `x-...` | anything | the owner's own keys (section 7) |

Only the key is required. A person with no name is reported.

### 4.5 A couple record

| Key | Shape | Notes |
|---|---|---|
| `events` | list of mappings | what happened to the couple: `marriage`, `divorce`, `engagement`, `civil-union`, `partnership`, `separation`, `annulment`, `end`, ... |
| `note` | text | a remark about the couple |
| `x-...` | anything | the owner's own keys |

A couple record is needed only when there is something to say. Two people who share a child are the child's
parents without one. An empty record (`a + b: {}`) says the two were a couple when nothing else is known. Both ids
MUST be people in the family; for an unknown partner, add a person record with no name.

**Whether a couple has ended.** Some events begin a couple (`marriage`, `civil-union`, `partnership`,
`engagement`) and some end it (`divorce`, `annulment`, `separation`, and `end`, meaning "it ended, the reason is
not known"). A couple has ended when it has an ending event that no beginning event follows. Events are ordered by
date; where a date is missing, by the order written. So married, divorced and married again is three events and the
couple has not ended. A partner's death never ends a couple, and a `FROM ... TO` span does not either: an ending
is always its own event.

### 4.6 Events

`events:` is a list of mappings. Each has a `type` and any of `date`, `place`, `note`, `cite` and `value`.

- `type` is a slug such as `occupation`, `residence`, `burial`, `immigration`. Hyphens read as spaces. Any slug is
  allowed; readers show unknown types as written.
- `value` carries the content of an attribute, such as the occupation `Mathematician`.
- A person's `events` MUST NOT contain `birth` or `death` (use the fields), SHOULD NOT contain more than one
  `burial` or more than one `cremation`, and SHOULD NOT contain couple-only types (`marriage`, `divorce`,
  `engagement`, `civil-union`, `partnership`, `separation`, `annulment`, `end`), which belong in the couple's record.

## 5. Dates

A `date` is one value everywhere. There are no separate start and end keys.

| Written | Meaning |
|---|---|
| `1850`, `1850-03`, `1850-03-15` | a year, a month, a day |
| `ABT 1850` (also `CAL`, `EST`) | about |
| `BEF 1920`, `AFT 1880` | before, after |
| `BET 1880 AND 1890` | some time between |
| `FROM 1900 TO 1950`, `FROM 1900`, `TO 1950` | a span, for things that last (a residence, an occupation) |
| `unknown` | happened, date not known |

The keywords are GEDCOM's and are accepted in any case. Each date inside a keyword form is a year, month or day as
in the first row. A span is reported on `birth`, `death`, and `marriage` or `divorce` events. For sorting, ages and
timelines a qualified date counts as its first year and is shown as approximate.

## 6. Checking

A conforming checker reports problems with the file name and line (`family.yml:214`) and never changes a file. An
error means the file cannot be used; a warning means something is ignored or probably wrong.

| Code | Level | When |
|---|---|---|
| `E-BAD-FAMILY` | error | the file cannot be parsed, is not a mapping, uses a merge key, or both `family.yml` and `family/` exist |
| `E-NO-FAMILY` | error | there is neither `family.yml` nor `family/` |
| `E-RECORD-KEY` | error | a top-level key is neither a person id nor a couple key |
| `E-RECORD-SHAPE` | error | a record is not a mapping; `name` is not a mapping; `parents` is not a list of ids; `events` is not a list of mappings; a dated fact is neither text nor a mapping |
| `E-DUPLICATE-ID` | error | the same person, or the same couple in either order, twice (also across split files) |
| `E-COUPLE-SELF` | error | a couple key names one person twice |
| `E-DANGLING-REF` | error | a parent, or either half of a couple key, is not a person in the family |
| `E-CYCLE` | error | a person is their own ancestor |
| `W-UNKNOWN-KEY` | warning | a key nothing reads, at any level; a suggestion is given when it looks like a misspelling (`birht` for `birth`) |
| `W-FLOW-COMMA` | warning | an empty key inside `{...}`: probably an unquoted comma |
| `W-BLANK` | warning | a known key with no value |
| `W-DUPLICATE-KEY` | warning | the same key twice in one mapping |
| `W-DATE-UNPARSED` | warning | a date that is not one of the forms in section 5 |
| `W-DATE-SPAN` | warning | a span on `birth`, `death`, or a `marriage` or `divorce` event |
| `W-END-BEFORE-START` | warning | an end date before its start |
| `W-BAD-SEX` | warning | `sex` is not one of the four words |
| `W-LIVING-FALSE` | warning | `living:` is not `true`; it is ignored |
| `W-EVENT-IS-FIELD` | warning | a `birth` or `death` entry in a person's `events` |
| `W-EVENT-ONCE` | warning | more than one `burial` or `cremation` for a person |
| `W-EVENT-PLACEMENT` | warning | a couple-only event type in a person's `events` |
| `W-NO-NAME` | warning | a person with no name |
| `W-TOO-MANY-PARENTS` | warning | more than two parents |

## 7. Your own keys

A key that starts with `x-` or `x_` (any case), such as `x-nickname`, belongs to the owner. A reader MUST keep it
when it rewrites the file and MUST NOT report it. It is allowed at every level.

## 8. Conformance

- `tests/conformance/valid/*.yml`: each MUST load with no issues and validate against `family.schema.json`.
- `tests/conformance/invalid/*.yml`: the first line is `# expect: CODE@LINE[, CODE@LINE ...]`; exactly that set of
  (code, line) pairs MUST be reported. An optional second line `# schema: rejects` says the JSON Schema rejects the
  file too.
- `cronicl schema` prints the JSON Schema for `family.yml`. Editors with YAML support use it to underline unknown
  keys and bad values as they are typed (`# yaml-language-server: $schema=family.schema.json` on the first line).

## 9. GEDCOM

`INDI` is a person and `FAM` a couple record. `FAMC`/`CHIL` become the child's `parents`. Individual events and
attributes (BAPM, CHR, CONF, BURI, CREM, IMMI, EMIG, NATU, RESI, OCCU, EDUC, RELI, NATI, GRAD, RETI, CENS, WILL,
PROB) become `events`; a family's MARR, DIV, ENGA and ANUL become events in the couple's record, of type `marriage`,
`divorce`, `engagement` and `annulment`. A `SOUR` line becomes `cite` and a `NOTE` becomes `note`. Anything that
cannot be mapped is set aside in `archive/gedcom-extra.yml`, keyed by person id, which nothing reads, and
`refs.gedcom` keeps the original record id. Export writes GEDCOM 5.5.1 (UTF-8); each distinct `cite` text becomes
one `SOUR` record.
