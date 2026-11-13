from __future__ import annotations

from pathlib import Path

ALLOWED = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
MAX_BYTES = 1_000_000


def safe_relative(value: str) -> bool:
    """A portrait path must stay inside media/: relative, forward slashes, no empty or `..` segments."""
    if not value or value.startswith("/") or "\\" in value:
        return False
    return all(segment not in ("", "..") for segment in value.split("/"))


def resolve(media_dir: Path, value: str) -> Path | None:
    """The portrait file, only if the path is safe, the file exists and its real path is inside `media_dir`."""
    if not safe_relative(value):
        return None
    media_dir = Path(media_dir)
    candidate = media_dir / value
    try:
        real = candidate.resolve()
        inside = real.is_relative_to(media_dir.resolve())
    except (OSError, ValueError):
        return None
    if not inside or not real.is_file():
        return None
    return candidate
