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
a record's id MUST be unique across them. Only the `.yml` files directly in `family/` are read; a `.yaml` file or a
subfolder there is not read and is reported, so that a branch is never lost without a word.

`family.yml` carries no version marker. The format version is the `schema_version` in `site.yml`: `3` is the only
value in use.

## 3. Reading the file

`family.yml` is YAML. A reader MUST:

- read every scalar as text exactly as typed: `NO` is the text `NO`, `1066` is the text `1066`, `2020-01-01` is
  text, not a date (YAML's "failsafe" schema);
- report a key that occurs twice in one mapping (the later value wins). Two *records* with the same key are `E-DUPLICATE-ID`: in
  one file the later one is used; across the files of `family/`, and for `a + b` followed by `b + a`, the first one is
  kept and the later one is ignored;
- reject merge keys (`<<`);
- accept UTF-8 text, with or without a byte-order mark and with either line ending, and a single YAML document
  (a second document is an error). YAML anchors and aliases (`&x`, `*x`) are allowed and are read as the text they
  stand for. Tabs cannot indent YAML, so a tab-indented file is a syntax error.

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
| `sex` | `male`, `female`, `unknown`, `other` | in any case; absent means unknown. Anything else, including `M` and `F`, is reported and read as unknown |
| `birth`, `death` | dated fact | a person with `death` is deceased |
| `parents` | list of at most two person ids | birth parents. A third is reported and ignored; the same id twice is reported |
| `adoptive-parents` | list of at most two person ids | the parents who adopted the person. A third is reported (`W-TOO-MANY-ADOPTIVE-PARENTS`) and ignored; the same id twice is reported. Either list may be absent: birth parents who are not known are left out, not invented. The adoption itself is an `events` entry of type `adoption`, whose `date` is optional. A reader that draws one set of parents per person SHOULD use `adoptive-parents` when it has any, and `parents` otherwise |
| `events` | list of mappings | see 4.6 |
| `portrait` | text | a path under `media/` |
| `living` | `true` | only to say someone is alive when their dates suggest otherwise (`yes`, `on` and `1` are read as `true`, in any case; any other value is reported and ignored). To say someone is dead, use `death`. `living: true` next to a `death` is reported, and the person is treated as living |
| `refs` | mapping | ids in other systems: `gedcom` (the record's id in an imported file), `gallery` (the person's id in a photo gallery) |
| `bio` | text | the biography, as markdown |
| `x-...` | anything | the owner's own keys (section 7) |

Only the key is required. A person with no name is reported, unless they are someone's partner or parent: a nameless record is the placeholder for an unknown partner or parent.

### 4.5 A couple record

| Key | Shape | Notes |
|---|---|---|
| `events` | list of mappings | what happened to the couple. Any `type` is allowed. `marriage`, `divorce`, `engagement`, `civil-union`, `partnership`, `separation`, `annulment` and `end` have a meaning (below); other types, such as `residence` or `census`, are kept as written. cronicl does not show them on the site yet, and writes them to GEDCOM as `EVEN`. A type that looks like a misspelling of one of the eight (`wedding`, `divorced`, `marraige`) is reported, because it would otherwise silently begin or end nothing |
| `note` | text | a remark about the couple |
| `x-...` | anything | the owner's own keys |

A couple record is needed only when there is something to say. Two people who share a child are the child's
parents without one. An empty record (`a + b: {}`) says the two were a couple when nothing else is known. Both ids
MUST be people in the family; for an unknown partner, add a person record with no name.

**Whether a couple has ended.** Some events begin a couple (`marriage`, `civil-union`, `partnership`,
`engagement`) and some end it (`divorce`, `annulment`, `separation`, and `end`, meaning "it ended, the reason is
not known"). A `type` is read in any case, with spaces or underscores as hyphens (`Civil Union` is `civil-union`). A couple has ended when it has an ending event that no beginning event follows. Events are ordered by
date; where a date is missing, by the order written. So married, divorced and married again is three events and the
couple has not ended. A partner's death never ends a couple, and a `FROM ... TO` span does not either: an ending
is always its own event.

The finer points, so that two implementations agree:

- Events are put in date order before they are read. A date that is not complete stands for a period: a beginning
  event sorts at the first day its date allows, an ending event at the last. So a divorce dated `1950` follows a
  marriage in `1950-06`, and one dated `1950-03` precedes a marriage in `1950-09`. Written order settles only events
  that land on the same day.
- An event with no date keeps the place where it was written among the others. An undated divorce written before a
  dated marriage therefore reads as "divorced, then married", and the couple has not ended. Put the date in.
- An engagement and a marriage are two partnerships, not one. A separation followed by a divorce or annulment is one
  partnership that ended for its final reason.

### 4.6 Events

`events:` is a list of mappings. Each has a `type` and any of `date`, `place`, `note`, `cite` and `value`.

- `type` is a slug such as `occupation`, `residence`, `burial`, `immigration`. Hyphens read as spaces. Any slug is
  allowed; readers show unknown types as written.
- `value` carries the content of an attribute, such as the occupation `Mathematician`.
- A person's `events` SHOULD NOT contain `birth` or `death` (use the fields), more than one `burial` or more than one
  `cremation`, or couple-only types (`marriage`, `divorce`, `engagement`, `civil-union`, `partnership`, `separation`,
  `annulment`, `end`), which belong in the couple's record. A checker reports each of these; nothing is dropped.
- `type` is required, on a couple's events as well as a person's.
- Where text is expected (`type`, `date`, `place`, `value`, `note`, and `cite` as text or a list of text) a list or
  mapping is an error. The same holds for every text field of a person record: `name` parts, `sex`, `portrait`,
  `bio`, `refs` values and the dated-fact keys.

### 4.7 Living and deceased

Privacy rules need to know who may be alive, so the format defines it. A person is **deceased** when they have a
`death` fact with a readable date, a span, `unknown`, or a place (`death: {place: Leeds}`). A `death` whose date is
not a date (`no`, `~`, `n/a`), or that has neither a date nor a place (`death: {note: still alive}`, `death: {}`), is
reported and does **not** count as a death: a value that only looks like "not dead" must never switch privacy off.

Whatever the death says, `living: true` makes a person living (a checker reports the conflict). Otherwise a person
with a counting death is deceased, and one without is **living** when they have no birth date, or when their birth
year is less than the cutoff ago. The cutoff is 100 years, or `privacy.cutoff_years` in `site.yml`. For this test only,
a qualified birth date counts as the **latest** year it allows (`BET 1920 AND 1950` is 1950; `ABT` and `BEF` use their
year), and `AFT` gives no usable year, so an uncertain date can never make a living person look dead. An old ancestor with a birth date and no `death` is
deceased once the cutoff has passed; one with no birth date is living until `death: unknown` is added.

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
in the first row. A year has exactly four digits (`0850`, not `850`); there are no negative or BC years. Qualifiers do
not nest (`BET ABT 1880 AND 1890` and `FROM ABT 1900` are not dates), and there is no other spelling: `c. 1850`,
`1850s`, `12 MAR 1850` and `March 1850` are reported as unreadable. The old form `~1850` is read as `ABT 1850`. A span is reported on `birth`, `death`, and `marriage` or `divorce` events, and so is a range that runs backwards, meaning the end
is certainly before the start (`BET 1890 AND 1880`, `FROM 1950 TO 1900`; `FROM 1950-06 TO 1950` is fine, since the
end may fall in the same year). For sorting, ages and
timelines a qualified date counts as its first year and is shown as approximate. A checker also reports dates that
contradict each other, using plain (unqualified) years only: a birth after the death, a child born before a parent,
and a child born more than a year after a parent died. These are warnings; a date is never changed.

## 6. Checking

A conforming checker reports problems with the file name and line (`family.yml:214`) and never changes a file. An
error means the file cannot be used; a warning means something is ignored or probably wrong. A checker may report more
than this table, for what belongs to the site and not to the format: portrait files, settings in `site.yml`, and
`E-GENERATION-CONFLICT`, which says the tree views cannot draw a person marrying their own ancestor or descendant
(a marriage between other relatives, such as an uncle and a niece, is drawn; some rarer tangles, such as a man
married to a woman and later to her daughter, can conflict too).

| Code | Level | When |
|---|---|---|
| `E-BAD-FAMILY` | error | the file cannot be parsed, is not a mapping, uses a merge key, or both `family.yml` and `family/` exist |
| `E-NO-FAMILY` | error | there is neither `family.yml` nor `family/` |
| `E-RECORD-KEY` | error | a top-level key is neither a person id nor a couple key |
| `E-RECORD-SHAPE` | error | a record is not a mapping; `name` or `refs` is not a mapping; `parents` is not a list of ids; `events` is not a list of mappings; a dated fact is neither text nor a mapping; a list or mapping where text is expected |
| `E-INVALID-ID` | error | a person id longer than 64 characters |
| `E-DUPLICATE-ID` | error | the same person, or the same couple in either order, twice (also across split files); which one is kept is in section 3 |
| `E-COUPLE-SELF` | error | a couple key names one person twice |
| `E-DANGLING-REF` | error | a parent, or either half of a couple key, is not a person in the family |
| `E-CYCLE` | error | a person is their own ancestor |
| `W-UNKNOWN-KEY` | warning | a key nothing reads, at any level; a suggestion is given when it looks like a misspelling (`birht` for `birth`) |
| `W-FLOW-COMMA` | warning | an empty key inside `{...}`: probably an unquoted comma |
| `W-BLANK` | warning | a known key with no value |
| `W-DUPLICATE-KEY` | warning | the same key twice in one mapping |
| `W-DATE-UNPARSED` | warning | a date that is not one of the forms in section 5. A `death` of this kind does not count as a death |
| `W-DATE-SPAN` | warning | a span on `birth`, `death`, or a `marriage` or `divorce` event |
| `W-END-BEFORE-START` | warning | an end date before its start, or a `BET` range that runs backwards |
| `W-BAD-SEX` | warning | `sex` is not one of the four words (in any case) |
| `W-LIVING-FALSE` | warning | `living:` is not `true`; it is ignored |
| `W-EVENT-IS-FIELD` | warning | a `birth` or `death` entry in a person's `events` |
| `W-EVENT-ONCE` | warning | more than one `burial` or `cremation` for a person |
| `W-EVENT-PLACEMENT` | warning | a couple-only event type in a person's `events` |
| `W-NO-NAME` | warning | a person with no name who is neither a partner nor a parent |
| `W-EVENT-NO-TYPE` | warning | an event with no `type` |
| `W-IGNORED-FILE` | warning | a `.yaml` file or a folder inside `family/`, which is not read |
| `W-DEATH-EMPTY` | warning | a `death` mapping with neither a date nor a place; it does not count as a death |
| `W-COUPLE-EVENT-TYPE` | warning | a couple event type that looks like a misspelling of `marriage`, `divorce`, ...; it is kept as written |
| `W-LIVING-AND-DEATH` | warning | `living: true` together with a `death` |
| `W-DUPLICATE-PARENT` | warning | the same parent listed twice |
| `W-BIRTH-AFTER-DEATH` | warning | a plain birth year after the plain death year |
| `W-CHILD-BEFORE-PARENT` | warning | a child born before a parent |
| `W-CHILD-AFTER-PARENT-DEATH` | warning | a child born more than a year after a parent died |
| `W-TOO-MANY-PARENTS` | warning | more than two parents |
| `W-TOO-MANY-ADOPTIVE-PARENTS` | warning | more than two adoptive parents |

## 7. Your own keys

A key that starts with `x-` or `x_` (any case), such as `x-nickname`, belongs to the owner. A reader MUST keep it
when it rewrites the file and MUST NOT report it. It is allowed inside records and inside the mappings of a record
(a name, a dated fact, an event). A key at the top level is always a record: `x-notes:` there is a person whose id
is `x-notes`, so keep your own notes inside a record.

## 8. Conformance

- `tests/conformance/valid/*.yml`: each MUST load with no issues and validate against `family.schema.json`.
- `tests/conformance/invalid/*.yml`: the first line is `# expect: CODE@LINE[, CODE@LINE ...]`; exactly that set of
  (code, line) pairs MUST be reported. An optional second line `# schema: rejects` says the JSON Schema rejects the
  file too.
- `cronicl schema` prints the JSON Schema for `family.yml`. Editors with YAML support use it to underline unknown
  keys and bad values as they are typed (`# yaml-language-server: $schema=family.schema.json` on the first line).

## 9. GEDCOM

`INDI` is a person and `FAM` a couple record. `FAMC`/`CHIL` become the child's `parents`; a `FAMC` with `PEDI adopted` (or the family named by the `FAMC` line
under an `ADOP` event) becomes `adoptive-parents`, and `ADOP` becomes an `adoption` event. Export writes the birth
family's `FAMC` first, then the adoptive one with `PEDI adopted`. `ADOP HUSB` or `ADOP WIFE` under the `FAMC` of an
`ADOP` event limits `adoptive-parents` to that one parent. Other `PEDI` values (`foster`, `sealing`) are not linked
(`W-PEDI-UNMAPPED` on import) and are set aside. Individual events and
attributes (BAPM, CHR, CONF, BURI, CREM, IMMI, EMIG, NATU, RESI, OCCU, EDUC, RELI, NATI, GRAD, RETI, CENS, WILL,
PROB, ADOP) become `events`; a family's MARR, DIV, ENGA and ANUL become events in the couple's record, of type `marriage`,
`divorce`, `engagement` and `annulment`. A `SOUR` line becomes `cite` and a `NOTE` becomes `note`. Anything that
cannot be mapped is set aside in `archive/gedcom-extra.yml`, keyed by person id, which nothing reads, and
`refs.gedcom` keeps the original record id. Export writes GEDCOM 5.5.1 (UTF-8); each distinct `cite` text becomes
one `SOUR` record.
