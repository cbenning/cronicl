"""The terminal interface: find people, edit them, add marriages, fix warnings. It sits on `cronicl.core`; nothing in
core or site imports it."""
from __future__ import annotations

from pathlib import Path


def run(data_dir: Path) -> int:
    """Open the TUI on a data folder and return the exit status."""
    from .app import CroniclApp

    CroniclApp(Path(data_dir)).run()
    return 0
