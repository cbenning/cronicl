from __future__ import annotations

from ..core.model import Tree
from ..core.relations import Relations


def home_person(tree: Tree, relations: Relations) -> str | None:
    """The person the owner chose with `home:` in site.yml, when it names someone; otherwise nobody.

    No person is picked on the owner's behalf: a default would be shown as the starting point and as the
    reference for every relationship line, with nothing telling the visitor who it is.
    """
    configured = (tree.site or {}).get("home")
    if configured and str(configured) in tree.people:
        return str(configured)
    return None
