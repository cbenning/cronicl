"""Edits made in the TUI wait here until the owner confirms them: the texts as loaded, the texts as edited, the checks
on the edited texts, the diff, and the one place anything is written."""
from __future__ import annotations

import difflib
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .model import Family, read_disk


class DiskChanged(Exception):
    """A file was changed by something else after it was loaded; nothing was written."""

    def __init__(self, names: list[str]) -> None:
        super().__init__("changed on disk: " + ", ".join(names))
        self.names = names


class Unreadable(Exception):
    """The edited text cannot be read as a family file; nothing was written."""


@dataclass
class FileDiff:
    name: str
    text: str  # a unified diff


def _stamp(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(data).hexdigest()


class Session:
    def __init__(self, data_dir: Path, today: date | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.today = today
        self.on_change = None  # called with no arguments after every stage, discard and commit
        self.reload()

    # ---- loading --------------------------------------------------------------------------------------------------
    def reload(self) -> None:
        """Read everything from disk again; staged changes are dropped."""
        self.site_text, files = read_disk(self.data_dir)
        self.loaded: dict[str, str] = dict(files)
        self.staged: dict[str, str] = dict(files)
        self.stamps = {name: _stamp(self.data_dir / name) for name in files}
        self._rebuild()

    def _rebuild(self) -> None:
        self.family = Family(self.data_dir, self.site_text, self.staged, self.today)
        if self.on_change:
            self.on_change()

    # ---- staging --------------------------------------------------------------------------------------------------
    @property
    def changed(self) -> bool:
        return any(self.staged.get(name) != text for name, text in self.loaded.items()) or any(name not in self.loaded for name in self.staged)

    def stage(self, name: str, text: str) -> None:
        self.staged[name] = text
        self._rebuild()

    def snapshot(self) -> dict[str, str]:
        return dict(self.staged)

    def restore(self, snapshot: dict[str, str]) -> None:
        """Put the staged texts back as they were when `snapshot` was taken."""
        self.staged = dict(snapshot)
        self._rebuild()

    def discard(self) -> None:
        self.staged = dict(self.loaded)
        self._rebuild()

    def changed_names(self) -> list[str]:
        return sorted(n for n, t in self.staged.items() if self.loaded.get(n) != t)

    def diff(self) -> list[FileDiff]:
        out = []
        for name in self.changed_names():
            old = self.loaded.get(name, "").splitlines(keepends=True)
            new = self.staged[name].splitlines(keepends=True)
            lines = difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}", n=3)
            out.append(FileDiff(name, "".join(line if line.endswith("\n") else line + "\n" for line in lines).replace("\r\n", "\n")))
        return out

    # ---- writing --------------------------------------------------------------------------------------------------
    def commit(self) -> None:
        """Write every changed file; refuse (writing nothing) if any file changed on disk or the result is unreadable."""
        names = self.changed_names()
        if any(i.code == "E-BAD-FAMILY" for i in self.family.issues):
            raise Unreadable("the edited text cannot be read as a family file")
        stale = []
        for name in names:
            path = self.data_dir / name
            if name in self.stamps:
                if not path.is_file() or _stamp(path) != self.stamps[name]:
                    stale.append(name)
            elif path.exists():
                stale.append(name)
        if stale:
            raise DiskChanged(stale)
        for name in names:
            self._write(self.data_dir / name, self.staged[name])
        self.reload()

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(text.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                shutil.copymode(path, temp)
            os.replace(temp, path)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
