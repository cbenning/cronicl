from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .dates import from_gedcom
from .issues import Issue
from .model import Event, Partnership, Person
from .slug import natural_key, person_slug, slugify, unique_id
from .store import load_tree, person_path, write_person


class GedcomError(Exception):
    """The GEDCOM file cannot be read."""


@dataclass
class Node:
    level: int
    tag: str
    value: str = ""
    xref: str | None = None
    children: list["Node"] = field(default_factory=list)


_LINE = re.compile(r"^\s*(\d+)\s+(?:(@[^@\s]+@)\s+)?(\S+)(?:\s(.*))?$")
_CHAR = re.compile(r"^\s*1\s+CHAR\s+(\S+)", re.M | re.I)


def decode_gedcom(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="strict")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    head = data[:4096].decode("ascii", errors="ignore")
    match = _CHAR.search(head)
    charset = match.group(1).upper() if match else "UTF-8"
    try:
        if charset in ("UTF-8", "UTF8"):
            return data.decode("utf-8")
        if charset in ("ASCII", "ANSI", "WINDOWS-1252", "CP1252", "IBM WINDOWS", "IBM-WINDOWS"):
            return data.decode("cp1252", errors="replace")
        if charset in ("UNICODE", "UTF-16"):
            return data.decode("utf-16")
    except UnicodeDecodeError as exc:
        raise GedcomError(f"file is not valid {charset}: {exc}") from exc
    if charset == "ANSEL":
        raise GedcomError("ANSEL encoding is not supported; re-export the file as UTF-8")
    raise GedcomError(f"unsupported character set {charset!r}")


def parse_nodes(text: str) -> tuple[list[Node], list[Issue]]:
    roots: list[Node] = []
    issues: list[Issue] = []
    stack: list[Node] = []
    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        if not raw.strip():
            continue
        match = _LINE.match(raw)
        if not match:
            issues.append(Issue("W-GEDCOM-LINE", f"line {number}: cannot parse {raw[:40]!r}"))
            continue
        level = int(match.group(1))
        xref, tag, value = match.group(2), match.group(3), match.group(4) or ""
        while stack and stack[-1].level >= level:
            stack.pop()
        if level == 0:
            node = Node(0, tag.upper(), value, xref)
            roots.append(node)
            stack = [node]
            continue
        if not stack:
            raise GedcomError(f"line {number}: content appears before the first level-0 record")
        parent = stack[-1]
        if level != parent.level + 1:
            issues.append(Issue("W-GEDCOM-LEVEL", f"line {number}: level jumps from {parent.level} to {level}"))
        upper = tag.upper()
        if upper == "CONT":
            parent.value += "\n" + value
            continue
        if upper == "CONC":
            parent.value += value
            continue
        node = Node(level, upper, value, xref)
        parent.children.append(node)
        stack.append(node)
    return roots, issues


# ------------------------------------------------------------ import mapping

_NAME = re.compile(r"^\s*([^/]*)(?:/([^/]*)/)?\s*(.*?)\s*$")


@dataclass
class ImportResult:
    people: list[Person]
    families: int
    issues: list[Issue]
    skipped: dict[str, int]


class ImportRefused(Exception):
    """The data directory is not in a state where an import is safe."""


def _node_lines(node: Node) -> list[str]:
    head = str(node.level)
    if node.xref:
        head += f" {node.xref}"
    head += f" {node.tag}"
    parts = node.value.split("\n") if node.value else [""]
    lines = [head + (f" {parts[0]}" if parts[0] else "")]
    lines += [f"{node.level + 1} CONT {part}" for part in parts[1:]]
    for child in node.children:
        lines += _node_lines(child)
    return lines


def _lines(nodes: list[Node]) -> str | None:
    out: list[str] = []
    for node in nodes:
        out += _node_lines(node)
    return "\n".join(out) or None


def _event(node: Node, label: str, owner: str, extra: list[Node], issues: list[Issue]) -> Event:
    """Map a BIRT/DEAT/MARR node; unmapped sub-lines are appended to `extra`."""
    date = place = None
    leftovers: list[Node] = []
    for child in node.children:
        if child.tag == "DATE" and date is None:
            value, ok = from_gedcom(child.value)
            date = value or None
            if value and not ok:
                issues.append(Issue("W-DATE-UNPARSED", f"{owner}: {label} date {value!r} kept as text"))
            if child.children:
                leftovers.append(child)
        elif child.tag == "PLAC" and place is None:
            place = child.value.strip() or None
            if child.children:
                leftovers.append(child)
        else:
            leftovers.append(child)
    if leftovers:
        extra.append(Node(node.level, node.tag, "", None, leftovers))
    return Event(date=date, place=place)


def _parse_name(node: Node, extra: list[Node]) -> tuple[str | None, str | None]:
    match = _NAME.match(node.value)
    given_part, surname, suffix = (match.group(1) or "").strip(), match.group(2), match.group(3)
    given = " ".join(part for part in (given_part, suffix) if part) or None
    surname = surname.strip() if surname and surname.strip() else None
    leftovers = []
    for child in node.children:
        if child.tag == "GIVN" and child.value.strip():
            given = child.value.strip()
        elif child.tag == "SURN" and child.value.strip():
            surname = child.value.strip()
        else:
            leftovers.append(child)
    if leftovers:
        extra.append(Node(node.level, node.tag, "", None, leftovers))
    return given, surname


def _is_pointer(value: str) -> bool:
    return value.startswith("@") and value.endswith("@")


def _person_from(node: Node, issues: list[Issue]) -> tuple[Person, str | None]:
    """Return (person with a placeholder id, first FAMC xref)."""
    xref = node.xref.strip("@")
    extra: list[Node] = []
    given = surname = None
    sex = "U"
    birth = death = None
    famc: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    for child in node.children:
        tag = child.tag
        if tag == "NAME" and "NAME" not in seen:
            seen.add("NAME")
            given, surname = _parse_name(child, extra)
        elif tag == "SEX" and "SEX" not in seen:
            seen.add("SEX")
            value = child.value.strip().upper()
            if value in ("M", "F"):
                sex = value
            elif value not in ("", "U"):
                extra.append(child)  # keep unrecognised values (e.g. X) verbatim
        elif tag == "BIRT" and "BIRT" not in seen:
            seen.add("BIRT")
            birth = _event(child, "birth", xref, extra, issues)
        elif tag == "DEAT" and "DEAT" not in seen:
            seen.add("DEAT")
            death = _event(child, "death", xref, extra, issues)
        elif tag == "FAMC":
            if not famc:
                famc.append(child.value.strip())
                if child.children:
                    extra.append(child)  # e.g. 2 PEDI adopted
            else:
                extra.append(child)
        elif tag == "FAMS":
            continue  # derived from the FAM records
        elif tag == "NOTE" and child.value and not _is_pointer(child.value.strip()):
            notes.append(child.value)
            if child.children:
                extra.append(child)  # e.g. 2 SOUR under the note
        else:
            extra.append(child)
    person = Person(
        id=f"@{xref}",
        given=given,
        surname=surname,
        sex=sex,
        birth=birth,
        death=death,
        gedcom_id=xref,
        gedcom_extra=_lines(extra),
        body="\n\n".join(notes),
    )
    return person, (famc[0] if famc else None)


def import_nodes(nodes: list[Node]) -> ImportResult:
    issues: list[Issue] = []
    skipped: dict[str, int] = {}
    indi_nodes: list[Node] = []
    fam_nodes: list[Node] = []
    for node in nodes:
        if node.tag == "INDI" and node.xref:
            indi_nodes.append(node)
        elif node.tag == "FAM" and node.xref:
            fam_nodes.append(node)
        else:
            skipped[node.tag] = skipped.get(node.tag, 0) + 1
    indi_nodes.sort(key=lambda n: natural_key(n.xref.strip("@")))
    fam_nodes.sort(key=lambda n: natural_key(n.xref.strip("@")))

    people: list[Person] = []
    first_famc: dict[str, str | None] = {}
    for node in indi_nodes:
        person, famc = _person_from(node, issues)
        people.append(person)
        first_famc[person.gedcom_id] = famc

    taken: set[str] = set()
    id_by_xref: dict[str, str] = {}
    for person in people:
        if person.given or person.surname:
            base = person_slug(person.given, person.surname)
        else:
            base = slugify(f"unknown-{person.gedcom_id}") or "person"
        person.id = unique_id(base, taken)
        taken.add(person.id)
        id_by_xref[person.gedcom_id] = person.id
    person_by_xref = {p.gedcom_id: p for p in people}
    person_by_id = {p.id: p for p in people}

    fam_order: list[str] = []
    fam_partners: dict[str, list[str]] = {}
    fam_children: dict[str, list[str]] = {}
    fam_marriage: dict[str, Event | None] = {}
    fam_extra: dict[str, list[Node]] = {}
    for node in fam_nodes:
        xref = node.xref.strip("@")
        extra: list[Node] = []
        partners: list[str] = []
        chil: list[str] = []
        marr_nodes: list[Node] = []
        for child in node.children:
            tag = child.tag
            if tag in ("HUSB", "WIFE"):
                target = child.value.strip().strip("@")
                if target in id_by_xref:
                    if id_by_xref[target] not in partners:
                        partners.append(id_by_xref[target])
                else:
                    issues.append(Issue("W-DANGLING-PARTNER", f"{xref}: {tag} {child.value!r} is not a known person"))
                    extra.append(child)
            elif tag == "CHIL":
                target = child.value.strip().strip("@")
                if target in person_by_xref:
                    chil.append(target)
                else:
                    issues.append(Issue("W-DANGLING-CHILD", f"{xref}: CHIL {child.value!r} is not a known person"))
                    extra.append(child)
            elif tag == "MARR":
                marr_nodes.append(child)
            else:
                extra.append(child)
        marriage = None
        for index, marr in enumerate(marr_nodes):
            if index == 0 and len(partners) >= 2:
                marriage = _event(marr, "marriage", xref, extra, issues)
            else:
                extra.append(marr)
        fam_order.append(xref)
        fam_partners[xref] = partners
        fam_children[xref] = chil
        fam_marriage[xref] = marriage
        fam_extra[xref] = extra

    for person in people:
        famc = first_famc[person.gedcom_id]
        if famc is None:
            continue
        key = famc.strip("@")
        if key in fam_partners:
            person.parents = list(fam_partners[key])
        else:
            issues.append(Issue("W-DANGLING-FAMC", f"{person.gedcom_id}: FAMC {famc!r} is not a known family"))
            person.gedcom_extra = "\n".join(filter(None, [person.gedcom_extra, f"1 FAMC {famc}"]))

    for xref in fam_order:
        partners = fam_partners[xref]
        for child_xref in fam_children[xref]:
            child = person_by_xref.get(child_xref)
            if child is None:
                continue
            famc = first_famc[child_xref]
            if famc is None:
                if partners:
                    child.parents = list(partners)
                    issues.append(
                        Issue(
                            "W-CHIL-WITHOUT-FAMC",
                            f"{child_xref}: listed as CHIL of {xref} without a matching FAMC; linked",
                        )
                    )
            elif famc.strip("@") != xref:
                issues.append(
                    Issue("W-CHIL-CONFLICT", f"{child_xref}: CHIL of {xref} but FAMC points at {famc}; kept FAMC")
                )

    for xref in fam_order:
        partners = fam_partners[xref]
        owner = person_by_id[min(partners)] if partners else None
        marriage = fam_marriage[xref]
        if len(partners) >= 2 and owner is not None:
            other = max(partners)
            if marriage is not None and not marriage.is_empty():
                owner.partnerships.append(Partnership(other, "marriage", marriage.date, place=marriage.place))
            elif not fam_children[xref]:
                owner.spouse.append(other)
        extra_nodes = fam_extra[xref]
        if extra_nodes:
            block = _lines([Node(0, "FAM", "", f"@{xref}@", extra_nodes)])
            target = owner
            if target is None:
                for child_xref in fam_children[xref]:
                    if child_xref in person_by_xref:
                        target = person_by_xref[child_xref]
                        break
            if target is None:
                issues.append(Issue("W-FAM-EXTRA-DROPPED", f"{xref}: family has no members; its extra data was dropped"))
            else:
                target.gedcom_extra = "\n".join(filter(None, [target.gedcom_extra, block]))

    return ImportResult(people=people, families=len(fam_nodes), issues=issues, skipped=skipped)


def write_import(result: ImportResult, data_dir: Path, source: bytes, source_name: str) -> dict:
    data_dir = Path(data_dir)
    existing, _ = load_tree(data_dir)
    if any(p.gedcom_id for p in existing.people.values()):
        raise ImportRefused(
            "data directory already contains imported records (gedcom_id set); re-import is not supported in v0.1"
        )
    for person in result.people:
        if person_path(data_dir, person.id).exists():
            raise ImportRefused(f"{person_path(data_dir, person.id)} already exists")
    for person in result.people:
        write_person(data_dir, person)
    digest = hashlib.sha256(source).hexdigest()[:8]
    archive = data_dir / "archive" / f"{Path(source_name).stem}-{digest}.ged"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(source)
    return {"people": len(result.people), "families": result.families, "archive": str(archive)}
