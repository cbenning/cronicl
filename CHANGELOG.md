# Changelog

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
