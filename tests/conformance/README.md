# family.yml conformance suite

These files define what a correct `family.yml` reader and checker must do, independently of the Python code that
passes them. Another implementation (any language) conforms when it reproduces every expectation below.

- `valid/*.yml`: each must load with **no issues** at all, and validate against `family.schema.json` (`cronicl schema`).
- `invalid/*.yml`: the first line is `# expect: CODE@LINE[, CODE@LINE ...]`: exactly this set of (issue code, line)
  pairs must be reported, no more and no fewer. Lines count from 1 in the file as written, including the comment.
  An optional second line `# schema: rejects` says the JSON Schema must reject the file too.
- Issue codes and their meaning are in `docs/superpowers/specs/2026-11-14-family-file-design.md` (section "Checking").
- Checks that need a folder rather than one file (`E-NO-FAMILY`, `family/` split duplicates, `E-BAD-FAMILY` for having
  both `family.yml` and `family/`) are covered by the Python tests, not here.
- Values are read as text exactly as typed; a reader must not turn `NO`, `1066` or `2020-01-01` into booleans,
  numbers or dates.
