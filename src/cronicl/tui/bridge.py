"""Running the existing command functions from the TUI without letting them print over the screen."""
from __future__ import annotations

import contextlib
import io
from argparse import Namespace
from pathlib import Path


def call(func, **options) -> tuple[int, str]:
    """Call a `cmd_*` function of cronicl.cli with these options; return (exit status, what it printed)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = func(Namespace(**options))
    return code, (out.getvalue() + err.getvalue()).strip()


def folder(data_dir: Path) -> str:
    return str(data_dir)
