from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import secrets
import subprocess
import sys
from datetime import date
from pathlib import Path

from .checks import check_all
from .core.edit import EditError
from .core.familyedit import plan_mark, plan_rename
from .core.inplace import InplaceError
from .core.migrate import MigrateRefused, apply_migration, plan_migration
from .core.gaps import find_gaps
from .core.gedcom import GedcomError, ImportRefused, decode_gedcom, import_nodes, parse_nodes, write_import_family
from .core.generations import LayoutError
from .core.new import append_text, plan_new_family
from .core.show import describe
from .core.living import is_living
from .site.settings import privacy_settings
from .core.relations import build_relations
from .site.render import build_site, dumps
from .core.schema import FAMILY_SCHEMA
from .core.search import search_people
from .core.store import load_tree

SITE_YML = """\
title: Family Tree
schema_version: 3
privacy:
  living: full          # full (default: nothing hidden) | placeholder | hidden -- redaction is opt-in
  cutoff_years: 100
  id_salt: {salt}
"""


def _summary(issues, severity: str, lead: str) -> str:
    chosen = [i for i in issues if i.severity == severity]
    if not chosen:
        return ""
    counts: dict[str, int] = {}
    for issue in chosen:
        counts[issue.code] = counts.get(issue.code, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    parts = [f"{n} {code}" for code, n in ordered[:5]]
    if len(ordered) > 5:
        parts.append("...")
    return f"{lead}{len(chosen)} {severity}{'' if len(chosen) == 1 else 's'}: {', '.join(parts)} (run cronicl check for details)"


def warning_summary(issues) -> str:
    """One line standing in for the individual warnings of a build; `cronicl check` has the details."""
    return _summary(issues, "warning", "")


def error_summary(issues) -> str:
    """What a build forced to continue with --ignore-errors says it is ignoring."""
    return _summary(issues, "error", "ignoring ")


def _print_issues(issues, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([i.to_dict() for i in issues], indent=2))
        return
    for issue in issues:
        where = f"{issue.path}:{issue.line}" if issue.path and issue.line else (issue.path or "-")
        print(f"{issue.severity.upper():7} {issue.code} {where}: {issue.message}")


def _git_dirty(path: Path) -> bool | None:
    try:
        inside = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
        )
    except FileNotFoundError:
        return None
    if inside.returncode != 0:
        return None
    status = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True)
    return bool(status.stdout.strip())


FAMILY_YML = """\
# yaml-language-server: $schema=family.schema.json
# family.yml: the whole family, in one file.
#
# A person is a record keyed by an id (surname first is a good habit); a couple is a record keyed by two ids
# joined by a plus sign. A child names its parents, so nothing is written twice.
#
# lovelace-ada:
#   name: {given: Augusta Ada, surname: Lovelace}
#   birth: {date: 1815-12-10, place: "London, England"}
#   death: 1852-11-27
#   parents: [byron-george, milbanke-annabella]
#
# king-william + lovelace-ada:
#   events:
#     - {type: marriage, date: 1835-07-08, place: "Ockham, Surrey"}
#
# Add people with `cronicl new`, check the file with `cronicl check`, see the result with `cronicl serve`.
"""


def cmd_init(args) -> int:
    root = Path(args.dir)
    root.mkdir(parents=True, exist_ok=True)
    site = root / "site.yml"
    if site.exists():
        print(f"error: {site} already exists", file=sys.stderr)
        return 2
    for folder in ("archive", "media"):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / ".gitkeep").touch()
    site.write_text(SITE_YML.format(salt=secrets.token_hex(8)), encoding="utf-8")
    (root / "family.yml").write_text(FAMILY_YML, encoding="utf-8")
    (root / "family.schema.json").write_text(dumps(FAMILY_SCHEMA), encoding="utf-8")
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("out/\n", encoding="utf-8")
    print(f"initialised {root}")
    return 0


def cmd_check(args) -> int:
    tree, load_issues = load_tree(Path(args.dir))
    issues = check_all(tree, load_issues)
    _print_issues(issues, args.format)
    failing = issues if args.strict else [i for i in issues if i.severity == "error"]
    return 1 if failing else 0


def cmd_import(args) -> int:
    source = Path(args.file)
    data = source.read_bytes()
    nodes, parse_issues = parse_nodes(decode_gedcom(data))
    result = import_nodes(nodes)
    for issue in parse_issues + result.issues:
        print(f"{issue.severity.upper():7} {issue.code}: {issue.message}")
    print(
        f"{len(result.people)} people, {result.families} families, "
        f"skipped records: {result.skipped or 'none'}"
    )
    if not args.apply:
        print("dry run; re-run with --apply (-a) to write files")
        return 0
    summary = write_import_family(result, Path(args.dir), data, source.name)
    print(f"wrote {summary['people']} people; archived source at {summary['archive']}")
    return 0


def cmd_build(args) -> int:
    root = Path(args.dir)
    tree, load_issues = load_tree(root)
    issues = check_all(tree, load_issues)
    errors = [i for i in issues if i.severity == "error"]
    if errors and not args.ignore_errors:
        _print_issues(errors, "text")
        print("error: fix the problems above or use --ignore-errors", file=sys.stderr)
        return 1
    summary = warning_summary(issues)
    if summary:
        print(summary)
    if errors:  # only reachable with --ignore-errors
        print(error_summary(errors))
        if privacy_settings(tree.site).broken:
            print("privacy setting unusable: living people are treated as placeholders")
    today = date.today()
    privacy = privacy_settings(tree.site)
    if privacy.living == "full":
        living = sum(1 for person in tree.people.values() if is_living(person, today, privacy.cutoff_years))
        if living:
            who = "1 person is" if living == 1 else f"{living} people are"
            print(
                f"WARNING W-PRIVACY-OFF site.yml: {who} treated as living and privacy.living is \"full\"; "
                "set it to placeholder or hidden before publishing"
            )
    out = Path(args.out) if args.out else root / "out"
    for folder in ("family", "media"):
        # a build clears what it generates in the output folder; never let that be the data itself
        data = (root / folder).resolve()
        if (out / folder).resolve() == data or out.resolve() == data or data in out.resolve().parents:
            print(f"error: --out {out} would overwrite the data folder {root / folder}; choose another folder", file=sys.stderr)
            return 2
    summary = build_site(tree, out, today=today, media_dir=root / "media")
    print(f"built {summary.people} people, {summary.files} files into {out}")
    return 0


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """A debugging server should always show the build that was just made, never a browser's cached copy."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def make_server(out: Path, port: int) -> http.server.ThreadingHTTPServer:
    # ThreadingHTTPServer sets SO_REUSEADDR, so restarting serve right after stopping it does not fail to bind.
    handler = functools.partial(NoCacheHandler, directory=str(out))
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def cmd_serve(args) -> int:
    code = cmd_build(args)
    if code != 0:
        return code
    out = Path(args.out) if args.out else Path(args.dir) / "out"
    with make_server(out, args.port) as httpd:
        print(f"serving {out} at http://127.0.0.1:{args.port}/ (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def _cmd_edit_family(args) -> int:
    root = Path(args.dir)
    results = plan_mark(root, args.ids, args.living)
    final: dict[Path, str] = {}
    for _, path, _, text in results:
        final[path] = text
    word = "set" if args.apply else "would set"
    what = "living: true" if args.living else "death: unknown"
    for pid, path, changed, _ in results:
        print(f"{pid} ({path.relative_to(root).as_posix()}): " + (f"{word} {what}" if changed else "unchanged"))
    if args.apply:
        for path, text in final.items():
            path.write_bytes(text.encode("utf-8"))
    elif any(changed for _, _, changed, _ in results):
        print("dry run; re-run with --apply (-a) to write these changes")
    return 0


def cmd_migrate(args) -> int:
    root = Path(args.dir)
    try:
        plan = plan_migration(root)
    except MigrateRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{plan.people} people, {plan.couples} couple records, {plan.events} events -> family.yml")
    for note in plan.notes:
        print(f"NOTE {note}")
    print("the old people/ folder moves to archive/people-md/; site.yml gets schema_version: 3")
    if not args.apply:
        print("dry run; re-run with --apply (-a) to write these changes")
        return 0
    if _git_dirty(root) and not args.allow_dirty:
        print("error: git working tree has uncommitted changes; commit them or use --allow-dirty", file=sys.stderr)
        return 2
    apply_migration(root, plan)
    print(f"migrated {plan.people} people into family.yml")
    return 0


def cmd_rename(args) -> int:
    root = Path(args.dir)
    changes = plan_rename(root, args.old, args.new)
    for change in changes:
        print(f"{change.path.relative_to(root).as_posix()}: {change.count} replacement{'' if change.count == 1 else 's'}")
    if not changes:
        print(f"{args.old} appears nowhere else; only its record key needs changing")
    if not args.apply:
        print("dry run; re-run with --apply (-a) to write these changes")
        return 0
    for change in changes:
        change.path.write_bytes(change.text.encode("utf-8"))
    print(f"renamed {args.old} to {args.new}")
    return 0


def cmd_edit_living(args) -> int:
    return _cmd_edit_family(args)


def cmd_gaps(args) -> int:
    tree, _ = load_tree(Path(args.dir))
    gaps = find_gaps(tree, build_relations(tree), today=date.today(), cutoff_years=privacy_settings(tree.site).cutoff_years)
    if args.limit is not None:
        gaps = gaps[: args.limit]
    if args.format == "json":
        print(json.dumps([g.to_dict() for g in gaps], indent=2, ensure_ascii=False))
    else:
        for g in gaps:
            print(f"{g.id}  {g.name}  missing: {', '.join(g.missing)}")
    return 0


def cmd_show(args) -> int:
    tree, _ = load_tree(Path(args.dir))
    if args.id not in tree.people:
        raise EditError(f"no person {args.id!r}; use cronicl search to find ids")
    print(describe(tree, build_relations(tree), args.id), end="")
    return 0


def _cmd_new_family(args) -> int:
    pid, target, text = plan_new_family(
        Path(args.dir), given=args.given, surname=args.surname, sex=args.sex, birth=args.birth,
        birth_place=args.birth_place, death=args.death, death_place=args.death_place, parents=args.parents or [],
        partners=args.partner or [], new_id=args.id, file=args.file,
    )
    rel = target.relative_to(Path(args.dir)).as_posix()
    if not args.apply:
        print(f"append to {rel}:")
        print(text, end="")
        print("dry run; re-run with --apply (-a) to write this")
        return 0
    append_text(target, text)
    print(f"added {pid} to {rel}")
    return 0


def cmd_new(args) -> int:
    return _cmd_new_family(args)


def cmd_search(args) -> int:
    tree, _ = load_tree(Path(args.dir))
    try:
        hits = search_people(tree, " ".join(args.query), today=date.today(), limit=args.limit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps([h.to_dict() for h in hits], indent=2, ensure_ascii=False))
    elif hits:
        id_width = max(len(h.id) for h in hits)
        name_width = max(len(h.name) for h in hits)
        years_width = max(len(h.years or "-") for h in hits)
        place_width = max(len(h.place or "-") for h in hits)
        for h in hits:
            marker = "*" if h.living else " "
            parents = ", ".join(h.parents) if h.parents else "-"
            print(
                f"{h.id:<{id_width}} {marker} {h.name:<{name_width}}  {(h.years or '-'):<{years_width}}  "
                f"{(h.place or '-'):<{place_width}}  parents: {parents}"
            )
        if any(h.living for h in hits):
            print("* = treated as living by the privacy rules (no death date and born <100 years ago, or undated)")
    return 0 if hits else 1


def cmd_schema(args) -> int:
    print(dumps(FAMILY_SCHEMA), end="")
    return 0


def _common() -> argparse.ArgumentParser:
    """Options shared by every command that works on a cronicl folder."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-C",
        "--dir",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="the cronicl folder (default: $CRONICL_DIR, else the current directory)",
    )
    return common


def _add_apply(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-a", "--apply", action="store_true", help="write the changes (default: preview only)")


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(
        prog="cronicl", description="Family tree file to static site", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", parents=[common], help="create a new cronicl folder")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("check", aliases=["validate"], parents=[common], help="report problems (read-only); also named validate")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("migrate", parents=[common], help="convert an old people/*.md folder to family.yml (preview unless --apply)")
    p.add_argument("--allow-dirty", action="store_true", help="run even if the git tree has uncommitted changes")
    _add_apply(p)
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("rename", parents=[common], help="change a person's id everywhere it is used (preview unless --apply)")
    p.add_argument("old", help="the current id")
    p.add_argument("new", help="the new id")
    _add_apply(p)
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("show", parents=[common], help="print one person as the site sees them (read-only)")
    p.add_argument("id", help="a person id (find ids with `cronicl search`)")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("search", parents=[common], help="fuzzy-find people and print their ids (read-only)")
    p.add_argument("query", nargs="+", help="words to look for in names, ids, years and places")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("gaps", parents=[common], help="list people with missing facts, best-connected first (read-only)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_gaps)

    p = sub.add_parser("new", parents=[common], help="add one person record to family.yml (preview unless --apply)")
    p.add_argument("--given")
    p.add_argument("--surname")
    p.add_argument("--sex", choices=["M", "F", "U", "male", "female", "unknown", "other"], default="U")
    p.add_argument("--id", help="the new person's id (default: surname-given)")
    p.add_argument("--partner", nargs="+", metavar="ID", help="also add an empty couple record with each of these people")
    p.add_argument("--file", help="for a family/ folder: the file to add to")
    p.add_argument("--birth", metavar="DATE")
    p.add_argument("--birth-place", metavar="PLACE")
    p.add_argument("--death", metavar="DATE")
    p.add_argument("--death-place", metavar="PLACE")
    p.add_argument("--parents", nargs="+", metavar="ID", help="one or two parent ids")
    _add_apply(p)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("import-gedcom", parents=[common], help="import a GEDCOM file (preview unless --apply)")
    p.add_argument("file", help="the .ged file to import")
    _add_apply(p)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("edit", parents=[common], help="state-changing helpers (edit person records)")
    edit_sub = p.add_subparsers(dest="edit_command", required=True)
    for name, living, helptext in (
        ("mark-deceased", False, "mark the named people deceased (`death: unknown` in family.yml)"),
        ("mark-living", True, "write `living: true` for the named people"),
    ):
        q = edit_sub.add_parser(name, parents=[common], help=helptext)
        q.add_argument("ids", nargs="+", help="person ids (find them with `cronicl search`)")
        _add_apply(q)
        q.set_defaults(func=cmd_edit_living, living=living)

    p = sub.add_parser("build", parents=[common], help="generate the static site")
    p.add_argument("--out", help="output folder (default: <dir>/out)")
    p.add_argument("--ignore-errors", action="store_true", help="build even if check reports errors")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("serve", parents=[common], help="build and serve locally")
    p.add_argument("--out", help="output folder (default: <dir>/out)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--ignore-errors", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("schema", help="print the JSON Schema for family.yml")
    p.set_defaults(func=cmd_schema)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.dir = getattr(args, "dir", None) or os.environ.get("CRONICL_DIR") or "."
    try:
        return args.func(args)
    except (GedcomError, ImportRefused, LayoutError, EditError, InplaceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
