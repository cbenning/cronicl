from __future__ import annotations

from pathlib import Path

from .dates import parse_date
from .edit import EditError
from .model import Event, Person
from .slug import person_slug, unique_id
from .store import load_tree


def plan_new(
    data_dir: Path,
    *,
    given: str | None,
    surname: str | None,
    sex: str = "U",
    birth: str | None = None,
    birth_place: str | None = None,
    death: str | None = None,
    death_place: str | None = None,
    parents: list[str] = (),
    spouse: list[str] = (),
    children: list[str] = (),
) -> Person:
    """The new person file as a Person; every input is checked before anything could be written."""
    data_dir = Path(data_dir)
    given, surname = (given or "").strip() or None, (surname or "").strip() or None
    if not (given or surname):
        raise EditError("give --given or --surname")
    if not (data_dir / "people").is_dir():
        raise EditError(f"{data_dir} is not a cronicl folder; run cronicl init")
    tree, _ = load_tree(data_dir)
    listed = [*parents, *spouse, *children]
    unknown = sorted({pid for pid in listed if pid not in tree.people})
    if unknown:
        raise EditError(f"unknown person id(s): {', '.join(unknown)}; use cronicl search to find ids")
    for pid in listed:
        if listed.count(pid) > 1:
            raise EditError(f"{pid} is listed twice")
    if len(parents) > 2:
        raise EditError("at most two parents")
    for value in (birth, death):
        if value and parse_date(value) is None:
            raise EditError(
                f"{value!r} is not a date (use YYYY, YYYY-MM or YYYY-MM-DD, with a leading ~ for approximate)"
            )
    return Person(
        id=unique_id(
            person_slug(given, surname),
            set(tree.people) | {path.stem for path in (data_dir / "people").glob("*.md")},  # never reuse a file name
        ),
        given=given,
        surname=surname,
        sex=sex,
        birth=Event(date=birth or None, place=birth_place or None) if (birth or birth_place) else None,
        death=Event(date=death or None, place=death_place or None) if (death or death_place) else None,
        parents=list(parents),
        spouse=list(spouse),
        children=list(children),
        id_pinned=True,
    )
