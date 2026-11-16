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


def init_family(data_dir: Path) -> tuple[int, str]:
    """`cronicl init`, or just the family file when site.yml is already there."""
    from .. import cli

    data_dir = Path(data_dir)
    if (data_dir / "site.yml").exists() and not (data_dir / "family.yml").exists() and not (data_dir / "family").is_dir():
        from ..core.schema import FAMILY_SCHEMA
        from ..site.render import dumps

        (data_dir / "family.yml").write_text(cli.FAMILY_YML, encoding="utf-8")
        (data_dir / "family.schema.json").write_text(dumps(FAMILY_SCHEMA), encoding="utf-8")
        return 0, "family.yml created"
    return call(cli.cmd_init, dir=str(data_dir))
