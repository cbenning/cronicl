"""The optional photo gallery shown on person pages.

`site.yml` carries one `gallery:` mapping. Core owns `type` and `label`; every other key belongs to the type.
Everything under `gallery:` is published to visitors' browsers, so it must never hold a secret.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .issues import Issue

CORE_KEYS = ("type", "label")
DEFAULT_LABEL = "Photos"
MAX_LABEL = 40
_SECRETISH = re.compile(r"token|secret|password|api[_-]?key", re.I)


@dataclass(frozen=True)
class GalleryType:
    name: str
    keys: tuple[str, ...]
    required: tuple[str, ...]
    browser: bool  # resolved in the visitor's browser (no build-time types exist yet)

    def __post_init__(self):
        clash = set(self.keys) & set(CORE_KEYS)
        if clash:
            raise ValueError(f"gallery type {self.name!r} cannot reuse the core keys {sorted(clash)}")


GALLERY_TYPES: dict[str, GalleryType] = {
    "fussel": GalleryType("fussel", keys=("url",), required=("url",), browser=True),
}


def _normal_url(value) -> str | None:
    """An http(s) address with a host, no query or fragment, ending in exactly one slash; else None."""
    if not isinstance(value, str):
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        return None
    return value.strip().rstrip("/") + "/"


def _label(value) -> str:
    text = str(value).strip()[:MAX_LABEL].strip() if value is not None else ""
    return text or DEFAULT_LABEL


def _type_of(gallery) -> GalleryType | None:
    if not isinstance(gallery, dict):
        return None
    return GALLERY_TYPES.get(gallery.get("type")) if isinstance(gallery.get("type"), str) else None


def gallery_config(site: dict) -> dict | None:
    """The normalised config of a valid gallery that resolves in the browser, else None. Never raises."""
    gallery = (site or {}).get("gallery")
    kind = _type_of(gallery)
    if kind is None or not kind.browser:
        return None
    url = _normal_url(gallery.get("url"))
    if url is None:
        return None
    return {"type": kind.name, "label": _label(gallery.get("label")), "url": url}


def gallery_issues(site: dict, people: dict) -> list[Issue]:
    issues: list[Issue] = []
    gallery = (site or {}).get("gallery")
    if gallery is not None:
        kind = _type_of(gallery)
        if kind is None:
            known = ", ".join(sorted(GALLERY_TYPES))
            issues.append(Issue("E-GALLERY-TYPE", f"gallery needs a mapping with a type, one of: {known}", "site.yml"))
        else:
            if "url" in kind.required and _normal_url(gallery.get("url")) is None:
                issues.append(
                    Issue("E-GALLERY-URL", "gallery url must be an http:// or https:// address without ? or #", "site.yml")
                )
            valid = set(CORE_KEYS) | set(kind.keys)
            for key in gallery:
                if key not in valid:
                    issues.append(
                        Issue("W-GALLERY-KEY", f"gallery key {str(key)!r} is not used; valid keys are {', '.join(sorted(valid))}", "site.yml")
                    )
                if _SECRETISH.search(str(key)):
                    issues.append(
                        Issue("W-GALLERY-SECRET", f"gallery key {str(key)!r} looks like a secret; everything under gallery is published to visitors", "site.yml")
                    )
    if gallery_config(site) is None:
        for person in people.values():
            if person.gallery_id:
                issues.append(
                    Issue("W-GALLERY-ID-UNUSED", f"{person.id}: gallery_id is set but no usable gallery is configured", person.location)
                )
    return issues
