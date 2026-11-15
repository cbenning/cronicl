"""Citations on the site: numbered footnotes on a person page and the data for the Sources page."""
from __future__ import annotations

from copy import deepcopy


def number_cites(groups) -> tuple[dict[str, int], list[dict]]:
    """Number each distinct citation text in order of first use. Returns ({text: n}, [{"n", "text"}...])."""
    numbers: dict[str, int] = {}
    for group in groups:
        for text in group:
            numbers.setdefault(text, len(numbers) + 1)
    return numbers, [{"n": n, "text": text} for text, n in numbers.items()]


def annotate(payload: dict) -> tuple[dict, list[dict]]:
    """A copy of a person payload whose `cite` lists hold {n, text, first}, and the numbered source list.

    Facts come first on the page, then the timeline. `first` marks the use a back-link points to. The payload that is
    written as JSON is left alone.
    """
    view = deepcopy(payload)
    items = [*view.get("facts", []), *view.get("events", [])]
    numbers, sources = number_cites(item.get("cite") or [] for item in items)
    seen: set[int] = set()
    for item in items:
        marked = []
        for text in item.get("cite") or []:
            n = numbers[text]
            marked.append({"n": n, "text": text, "first": n not in seen})
            seen.add(n)
        item["cite"] = marked
    return view, sources


def source_index(people: list[tuple[str, str, list[dict]]]) -> list[dict]:
    """Every distinct citation text with the people who cite it. `people` is [(id, name, sources of that page)]."""
    found: dict[str, dict[str, str]] = {}
    for pid, name, sources in people:
        for source in sources:
            found.setdefault(source["text"], {})[pid] = name
    return [
        {"text": text, "people": [{"id": pid, "name": by_id[pid]} for pid in sorted(by_id, key=lambda i: (by_id[i].casefold(), i))]}
        for text, by_id in sorted(found.items(), key=lambda item: (item[0].casefold(), item[0]))
    ]
