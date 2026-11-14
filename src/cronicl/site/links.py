from __future__ import annotations

from urllib.parse import quote


def valid_edit_url(value) -> bool:
    """An http(s) address that names the person: `{id}`, or the record's place in the file with `{file}` and `{line}`."""
    return isinstance(value, str) and value.startswith(("http://", "https://")) and ("{id}" in value or "{line}" in value)


def valid_contact(value) -> bool:
    return isinstance(value, str) and value.startswith(("mailto:", "http://", "https://"))


def page_links(site: dict, pid: str, name: str, source: str | None = None, line: int | None = None) -> list[dict]:
    """The optional links at the foot of a person page: edit this page, then suggest a correction.

    `{file}` and `{line}` in edit_url are the file holding the person's record and the record's first line; a person
    with no known file or line (redacted, or not from a family file) gets no edit link when the template needs them.

    Only http, https and mailto links are ever produced, and only from well-formed site.yml values.
    """
    links: list[dict] = []
    edit_url, contact = site.get("edit_url"), site.get("contact")
    if valid_edit_url(edit_url):
        needs_place = "{file}" in edit_url or "{line}" in edit_url
        if not needs_place or (source and line):
            href = edit_url.replace("{id}", pid).replace("{file}", source or "").replace("{line}", str(line or ""))
            links.append({"href": href, "text": "Edit this page"})
    if valid_contact(contact):
        href = contact
        if contact.startswith("mailto:"):
            href += "?subject=" + quote(f"Correction: {name} ({pid})", safe="")
        links.append({"href": href, "text": "Suggest a correction"})
    return links
