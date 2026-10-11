from __future__ import annotations

import argparse
import functools
import http.server
import json
import secrets
import socketserver
import subprocess
import sys
from datetime import date
from pathlib import Path

from .check import check_tree
from .fix import apply_plan, plan_fix
from .gedcom import GedcomError, ImportRefused, decode_gedcom, import_nodes, parse_nodes, write_import
from .layout import LayoutError
from .render import build_site, dumps
from .schema import PERSON_SCHEMA
from .store import load_tree

SITE_YML = """\
title: Family Tree
schema_version: 1
privacy:
  living: placeholder   # hidden | placeholder | full
  cutoff_years: 100
  id_salt: {salt}
"""


def _print_issues(issues, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([i.to_dict() for i in issues], indent=2))
        return
    for issue in issues:
        print(f"{issue.severity.upper():7} {issue.code} {issue.path or '-'}: {issue.message}")


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


def cmd_init(args) -> int:
    root = Path(args.dir)
    site = root / "site.yml"
    if site.exists():
        print(f"error: {site} already exists", file=sys.stderr)
        return 2
    for folder in ("people", "archive"):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / ".gitkeep").touch()
    site.write_text(SITE_YML.format(salt=secrets.token_hex(8)), encoding="utf-8")
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("out/\n", encoding="utf-8")
    print(f"initialised {root}")
    return 0


def cmd_check(args) -> int:
    tree, load_issues = load_tree(Path(args.dir))
    issues = check_tree(tree, load_issues)
    _print_issues(issues, args.format)
    failing = issues if args.strict else [i for i in issues if i.severity == "error"]
    return 1 if failing else 0


def cmd_fix(args) -> int:
    root = Path(args.dir)
    plan = plan_fix(root)
    for note in plan.notes:
        print(note)
    for issue in plan.unresolved:
        print(f"UNRESOLVED {issue.code} {issue.path or '-'}: {issue.message}")
    if plan.empty:
        print("nothing to fix")
        return 0
    if not args.apply:
        print("dry run; re-run with --apply to write these changes")
        return 0
    if _git_dirty(root) and not args.force:
        print("error: git working tree has uncommitted changes; commit them or use --force", file=sys.stderr)
        return 2
    apply_plan(plan)
    print(f"applied {len(plan.writes)} write(s), {len(plan.deletes)} delete(s)")
    return 0


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
        print("dry run; re-run with --apply to write files")
        return 0
    summary = write_import(result, Path(args.into), data, source.name)
    print(f"wrote {summary['people']} people; archived source at {summary['archive']}")
    return 0


def cmd_build(args) -> int:
    root = Path(args.dir)
    tree, load_issues = load_tree(root)
    issues = check_tree(tree, load_issues)
    errors = [i for i in issues if i.severity == "error"]
    if errors and not args.force:
        _print_issues(errors, "text")
        print("error: fix the problems above or use --force", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else root / "out"
    summary = build_site(tree, out, today=date.today())
    print(f"built {summary.people} people, {summary.files} files into {out}")
    return 0


def cmd_serve(args) -> int:
    code = cmd_build(args)
    if code != 0:
        return code
    out = Path(args.out) if args.out else Path(args.dir) / "out"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {out} at http://127.0.0.1:{args.port}/ (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_schema(args) -> int:
    print(dumps({"person": PERSON_SCHEMA}), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="famsite", description="Markdown family tree to static site")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a new data repository")
    p.add_argument("dir", nargs="?", default=".")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("check", help="report problems (read-only)")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("fix", help="repair filenames and ids (dry run unless --apply)")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--force", action="store_true", help="run even if the git tree is dirty")
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("import-gedcom", help="import a GEDCOM file (dry run unless --apply)")
    p.add_argument("file")
    p.add_argument("--into", default=".")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("build", help="generate the static site")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--out")
    p.add_argument("--force", action="store_true", help="build even if check reports errors")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("serve", help="build and serve locally")
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--out")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("schema", help="print the JSON Schema for frontmatter")
    p.set_defaults(func=cmd_schema)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (GedcomError, ImportRefused, LayoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
