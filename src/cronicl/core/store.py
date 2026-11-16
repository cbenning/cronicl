"""Loading a data folder: site.yml, and the family (family.yml or family/)."""
from __future__ import annotations

from pathlib import Path

from .family import has_family, read_family
from .issues import Issue
from .model import Tree
from .yamltext import load_text


def load_site(data_dir: Path) -> tuple[dict, list[Issue]]:
    path = Path(data_dir) / "site.yml"
    if not path.exists():
        return load_site_text(None)
    try:
        raw = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return {"_unreadable": True}, [Issue("E-BAD-SITE-YML", f"cannot read site.yml: {type(exc).__name__}", "site.yml")]
    return load_site_text(raw)


def load_site_text(raw: str | None) -> tuple[dict, list[Issue]]:
    """site.yml from its text (None when there is no file)."""
    if raw is None:
        return {}, [Issue("W-NO-SITE-YML", "site.yml not found; using defaults")]
    unreadable = {"_unreadable": True}  # the owner's intent is unknown, so settings fail closed
    result = load_text(raw)
    if result.error:
        return unreadable, [Issue("E-BAD-SITE-YML", f"cannot parse site.yml: {result.error}", "site.yml", result.error_line)]
    if result.merge_keys:
        return unreadable, [Issue("E-BAD-SITE-YML", "merge keys (<<) are not supported in site.yml; write the values out", "site.yml", result.merge_keys[0])]
    data = result.data
    if not isinstance(data, dict):
        return unreadable, [Issue("E-BAD-SITE-YML", "site.yml must be a mapping", "site.yml")]
    issues: list[Issue] = [
        Issue("W-DUPLICATE-KEY", f"duplicate key {key!r}; the later value is used", "site.yml", line) for key, line in result.duplicates
    ]
    version = data.get("schema_version")
    if version is not None and not (isinstance(version, str) and version.strip() in ("3",)):
        issues.append(Issue("E-SCHEMA-VERSION", f"unsupported schema_version {version!r}", "site.yml"))
    return data, issues


def load_tree(data_dir: Path) -> tuple[Tree, list[Issue]]:
    """The whole data folder: site settings and the family. A folder with no family file is an error that says how to start one."""
    data_dir = Path(data_dir)
    site, issues = load_site(data_dir)
    tree = Tree(site=site)
    if not has_family(data_dir):
        if (data_dir / "family.yaml").exists():
            hint = "; found family.yaml: rename it to family.yml"
        else:
            hint = "; run `cronicl init` to start one"
        return tree, issues + [Issue("E-NO-FAMILY", f"no family.yml (or family/ folder) in {data_dir}{hint}", "family.yml")]
    people, record_issues = read_family(data_dir)
    issues = issues + record_issues
    for person in people:
        tree.people[person.id] = person
    return tree, issues
