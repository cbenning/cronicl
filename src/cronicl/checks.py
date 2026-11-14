"""Everything `check` reports: the family (core) and site.yml (site), merged and sorted."""
from __future__ import annotations

from .core.check import _guard, check_tree
from .core.issues import Issue
from .core.model import Tree
from .site.config import site_check


def check_all(tree: Tree, load_issues: list[Issue] | None = None) -> list[Issue]:
    issues = check_tree(tree, load_issues)
    _guard("site.yml", lambda: issues.extend(site_check(tree.site or {}, tree.people)), issues, "site.yml")
    return sorted(issues, key=lambda i: (i.path or "", i.code, i.message))
