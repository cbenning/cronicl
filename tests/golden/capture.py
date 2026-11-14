"""Regenerates tests/golden/legacy-build from tests/fixtures/legacy using the LEGACY (pre-family.yml) code.

The golden files are the truth the migration acceptance test compares against. They were captured once, from the
old code, on 2026-11-14 with today fixed at 2026-10-10. Do not regenerate them from new code.

The fixture was last adjusted (one `marriages:` entry that merges cleanly instead of overlapping another union) and the golden
files regenerated at commit 941cab1 (pre-rename code, package `famsite`).

Usage (old code only, at that commit): python tests/golden/capture.py
"""
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from famsite.check import check_tree  # noqa: F401  (old module path)
from famsite.render import build_site
from famsite.store import load_tree

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "legacy"
OUT = ROOT / "tests" / "golden" / "legacy-build"
TODAY = date(2026, 10, 10)
KEEP = ("index.json", "layout.json", "timeline.json", "kin.json")


def capture(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        shutil.copytree(FIXTURE, data)
        site = (data / "site.yml").read_text(encoding="utf-8").replace("living: full", f"living: {mode}")
        (data / "site.yml").write_text(site, encoding="utf-8")
        tree, _ = load_tree(data)
        build = Path(tmp) / "out"
        build_site(tree, build, today=TODAY, media_dir=data / "media")
        target = OUT / mode
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for name in KEEP:
            shutil.copyfile(build / name, target / name)
        for folder in ("data/people", "focus"):
            (target / folder).mkdir(parents=True, exist_ok=True)
            for f in sorted((build / folder).glob("*.json")):
                shutil.copyfile(f, target / folder / f.name)


if __name__ == "__main__":
    for mode in ("full", "placeholder"):
        capture(mode)
    print("captured", OUT, file=sys.stderr)
