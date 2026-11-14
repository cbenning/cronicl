"""Errors shared by the commands that change a family."""
from __future__ import annotations


class EditError(Exception):
    """An edit command cannot be applied."""
