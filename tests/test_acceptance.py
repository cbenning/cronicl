"""A site built after `migrate` shows what the site built before it showed (compared against the golden build)."""
import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from cronicl.cli import main
from cronicl.core.dates import to_modern
from cronicl.core.store import load_tree
from cronicl.site.render import build_site

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "legacy"
GOLDEN = HERE / "golden" / "legacy-build"
TODAY = date(2026, 10, 10)

# Differences the family-file design intends, and only these. Keyed by (file, person id) -> JSON keys allowed to differ.
INTENDED = {
    # `living: false` with no death, and an importer's bare `DEAT Y`, become `death: unknown`: the page now says the
    # person died, date not known (before, it said nothing).
    ("data/people", "moss-ellen"): {"death", "summary"},
    ("data/people", "smith-amy"): {"death", "summary"},
}


# The golden files hold the old code's tree layout. Where the boxes and connectors are drawn is the layout's own
# business and has changed since (tests/test_layout.py covers it); the migration must still produce the same people,
# couples and connections, so only the positions in the layout files are left out of the comparison.
POSITIONS = re.compile(r"/(bounds/|(nodes|unions|labels)\[\d+\]/[xy]:|edges\[\d+\]/points)")


def migrated_copy(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    assert main(["migrate", "--dir", str(data), "--apply", "--allow-dirty"]) == 0
    return data


def build_mode(data: Path, mode: str, out: Path):
    site = (data / "site.yml").read_text(encoding="utf-8").replace("living: full", f"living: {mode}")
    (data / "site.yml").write_text(site, encoding="utf-8")
    tree, issues = load_tree(data)
    assert [i for i in issues if i.severity == "error"] == [], issues
    build_site(tree, out, today=TODAY, media_dir=data / "media")


def diff_json(a, b, path=""):
    """Readable differences between two JSON values."""
    if type(a) is not type(b):
        return [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'golden' if key in a else 'migrated'}")
            else:
                out += diff_json(a[key], b[key], f"{path}/{key}")
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff_json(x, y, f"{path}[{i}]")]
    return [] if a == b or (isinstance(a, str) and to_modern(a) == b) else [f"{path}: {a!r} != {b!r}"]


@pytest.mark.parametrize("mode", ["full", "placeholder"])
def test_the_migrated_site_matches_the_golden_build(tmp_path, mode):
    data = migrated_copy(tmp_path)
    out = tmp_path / "out"
    build_mode(data, mode, out)
    golden = GOLDEN / mode
    problems = []
    names = ["index.json", "layout.json", "timeline.json", "kin.json"]
    for folder in ("data/people", "focus"):
        names += sorted(f"{folder}/{p.name}" for p in (golden / folder).glob("*.json"))
        extra = {f"{folder}/{p.name}" for p in (out / folder).glob("*.json")} - set(names)
        problems += [f"unexpected file {name}" for name in sorted(extra)]
    for name in names:
        if not (out / name).exists():
            problems.append(f"missing {name}")
            continue
        old = json.loads((golden / name).read_text(encoding="utf-8"))
        new = json.loads((out / name).read_text(encoding="utf-8"))
        if isinstance(new, dict) and new.get("aka") == []:
            del new["aka"]  # a new payload field: "also known as", empty for everyone in the fixture
        folder, _, leaf = name.rpartition("/")
        allowed = INTENDED.get((folder, leaf[:-5]), set())
        drawn = name == "layout.json" or folder == "focus"
        for line in diff_json(old, new):
            if drawn and POSITIONS.match(line):
                continue
            if not any(line.startswith("/" + key) for key in allowed):
                problems.append(f"{name} {line}")
    assert problems == [], "\n".join(problems[:40])
