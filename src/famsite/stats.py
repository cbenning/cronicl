from __future__ import annotations

from .model import Tree
from .relations import Relations
from .slug import slugify


def _generations(relations: Relations, pids: list[str]) -> int:
    """The longest chain of parent links, counted in people."""
    memo: dict[str, int] = {}

    def depth(pid: str, visiting: frozenset[str]) -> int:
        if pid in memo:
            return memo[pid]
        best = 0
        for parent in relations.parents.get(pid, []):
            if parent not in visiting:  # a parent cycle is reported by check; do not loop on it
                best = max(best, depth(parent, visiting | {pid}))
        memo[pid] = best + 1
        return memo[pid]

    return max((depth(pid, frozenset()) for pid in pids), default=0)


def site_stats(tree: Tree, relations: Relations, timeline: dict) -> dict:
    """The numbers on the home page: people, generations, the span of years and every surname."""
    shown: dict[str, str] = {}
    counts: dict[str, int] = {}
    for pid in sorted(tree.people):
        surname = (tree.people[pid].surname or "").strip()
        slug = slugify(surname)
        if not slug:
            continue
        shown.setdefault(slug, surname)
        counts[slug] = counts.get(slug, 0) + 1
    ordered = sorted(counts, key=lambda slug: (-counts[slug], slug))
    span = timeline.get("range", {})
    return {
        "people": len(tree.people),
        "generations": _generations(relations, sorted(tree.people)),
        "first_year": span.get("min"),
        "last_year": span.get("max"),
        "surnames": [{"surname": shown[slug], "slug": slug, "count": counts[slug]} for slug in ordered],
    }
