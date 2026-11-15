"""Loading and checking a family from text (it sits beside checks.py because the site settings are checked too), so a proposed edit can be checked before anything is written."""
from __future__ import annotations

from pathlib import Path

from .checks import check_all
from .core.family import read_family_texts
from .core.issues import Issue
from .core.model import Tree
from .core.store import load_site_text


def load_tree_from_texts(site_text: str | None, files: dict[str, str], data_dir: Path = Path(".")) -> tuple[Tree, list[Issue]]:
    """The tree and the loader's issues for `files` (relative name -> text) and the text of site.yml (None: no file)."""
    site, issues = load_site_text(site_text)
    tree = Tree(site=site)
    people, record_issues = read_family_texts(files, data_dir)
    for person in people:
        tree.people[person.id] = person
    return tree, issues + record_issues


def check_texts(site_text: str | None, files: dict[str, str], data_dir: Path = Path(".")) -> list[Issue]:
    """Everything `cronicl check` would report for these texts."""
    tree, load = load_tree_from_texts(site_text, files, data_dir)
    return check_all(tree, load)
