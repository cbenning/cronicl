from __future__ import annotations

from urllib.parse import quote


def valid_edit_url(value) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://")) and "{id}" in value


def valid_contact(value) -> bool:
    return isinstance(value, str) and value.startswith(("mailto:", "http://", "https://"))


def page_links(site: dict, pid: str, name: str) -> list[dict]:
    """The optional links at the foot of a person page: edit this page, then suggest a correction.

    Only http, https and mailto links are ever produced, and only from well-formed site.yml values.
    """
    links: list[dict] = []
    edit_url, contact = site.get("edit_url"), site.get("contact")
    if valid_edit_url(edit_url):
        links.append({"href": edit_url.replace("{id}", pid), "text": "Edit this page"})
    if valid_contact(contact):
        href = contact
        if contact.startswith("mailto:"):
            href += "?subject=" + quote(f"Correction: {name} ({pid})", safe="")
        links.append({"href": href, "text": "Suggest a correction"})
    return links
