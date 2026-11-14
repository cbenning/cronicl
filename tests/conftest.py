from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def write():
    """Write text (as UTF-8 bytes, so CRLF is preserved) under root and return the path."""

    def _write(root: Path, rel: str, text: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    return _write


@pytest.fixture
def sample_ged() -> Path:
    return FIXTURES / "sample.ged"


@pytest.fixture
def make_tree():
    """Build an in-memory Tree from Person kwargs: make_tree([{"id": "a", "parents": ["b"]}, ...])."""
    from cronicl.core.model import Person, Tree

    def _make(people):
        tree = Tree()
        for spec in people:
            person = Person(**spec)
            tree.people[person.id] = person
        return tree

    return _make


@pytest.fixture
def write_family():
    """Write a family.yml (and a minimal site.yml) under root: write_family(root, "alder-ada:\\n  name: ...")."""

    def _write(root: Path, text: str, name: str = "family.yml") -> Path:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        site = root / "site.yml"
        if not site.exists():
            site.write_text("title: T\nschema_version: 3\n", encoding="utf-8")
        return path

    return _write
