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


def plan_new_family(
    data_dir: Path,
    *,
    given: str | None,
    surname: str | None,
    sex: str = "unknown",
    birth: str | None = None,
    birth_place: str | None = None,
    death: str | None = None,
    death_place: str | None = None,
    parents: list[str] = (),
    partners: list[str] = (),
    new_id: str | None = None,
    file: str | None = None,
):
    """What `new` would append to the family file: (id, target path, text). Everything is checked first."""
    from .dates import is_unknown, parse_date
    from .emit import couple, person
    from .family import has_family
    from .slug import is_valid_id

    data_dir = Path(data_dir)
    given, surname = (given or "").strip() or None, (surname or "").strip() or None
    if not (given or surname):
        raise EditError("give --given or --surname")
    if not has_family(data_dir):
        raise EditError(f"{data_dir} has no family.yml; run cronicl init (or cronicl migrate)")
    tree, _ = load_tree(data_dir)
    listed = [*parents, *partners]
    unknown = sorted({pid for pid in listed if pid not in tree.people})
    if unknown:
        raise EditError(f"unknown person id(s): {', '.join(unknown)}; use cronicl search to find ids")
    for pid in listed:
        if listed.count(pid) > 1:
            raise EditError(f"{pid} is listed twice")
    if len(parents) > 2:
        raise EditError("at most two parents")
    for value, label in ((birth, "--birth"), (death, "--death")):
        if value and not (is_unknown(value) or parse_date(value)):
            raise EditError(f"{label} {value!r} is not a date (use YYYY, YYYY-MM, YYYY-MM-DD, ABT/BEF/AFT/BET ..., or unknown)")
    word = {"M": "male", "F": "female", "U": "unknown"}.get(sex, sex)
    if word not in ("male", "female", "unknown", "other"):
        raise EditError("--sex must be male, female, unknown or other")
    if new_id:
        if not is_valid_id(new_id):
            raise EditError(f"{new_id!r} is not a valid id (lower-case letters, digits and single hyphens)")
        if new_id in tree.people:
            raise EditError(f"{new_id} already exists")
        pid = new_id
    else:
        pid = unique_id(person_slug(given, surname), set(tree.people))
    single, folder = data_dir / "family.yml", data_dir / "family"
    if single.exists():
        if file and file != "family.yml":
            raise EditError("this family is one file (family.yml); --file is for a family/ folder")
        target = single
    else:
        if not file:
            raise EditError("this family is split over several files; choose one with --file NAME.yml")
        if "/" in file or "\\" in file or not file.endswith(".yml") or file.startswith("."):
            raise EditError("--file must be a plain file name ending in .yml")
        target = folder / file
    spec = {
        "name": {"given": given, "surname": surname},
        "sex": word,
        "birth": {"date": birth, "place": birth_place} if (birth and birth_place) or (birth_place and not birth) else birth,
        "death": {"date": death, "place": death_place} if (death and death_place) or (death_place and not death) else death,
        "parents": list(parents),
    }
    text = person(pid, spec) + "".join(couple(pid, other) for other in partners)
    return pid, target, text


def append_text(target: Path, text: str) -> None:
    """Add `text` to the end of a family file, keeping its line endings and touching nothing that is already there."""
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_bytes() if target.exists() else b""
    crlf = b"\r\n" in existing
    newline = "\r\n" if crlf else "\n"
    body = text.replace("\n", newline)
    prefix = b""
    if existing and not existing.endswith(b"\n"):
        prefix += newline.encode()
    if existing.strip():
        prefix += newline.encode()  # a blank line between records
    with open(target, "ab") as handle:
        handle.write(prefix + body.encode("utf-8"))
