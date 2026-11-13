from __future__ import annotations

import subprocess
from pathlib import Path


def recent_changes(data_dir: Path, limit: int = 8) -> list[dict]:
    """People whose files changed most recently, newest first, each once: [{"id", "date": "YYYY-MM-DD"}].

    Read from the data folder's git history; a folder that is not a git repository (or no git) gives [].
    """
    data_dir = Path(data_dir)
    try:
        result = subprocess.run(
            ["git", "-C", str(data_dir), "log", "--relative", "--format=%x00%cs", "--name-only", "--", "people"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    found: list[dict] = []
    seen: set[str] = set()
    date = ""
    for line in result.stdout.splitlines():
        if line.startswith("\x00"):
            date = line[1:].strip()
            continue
        path = Path(line.strip())
        if not date or path.parent.name != "people" or path.suffix != ".md":
            continue
        if path.stem in seen or not (data_dir / path).is_file():
            continue
        seen.add(path.stem)
        found.append({"id": path.stem, "date": date})
        if len(found) >= limit:
            break
    return found
