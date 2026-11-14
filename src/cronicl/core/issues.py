from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    path: str | None = None
    line: int | None = None

    @property
    def severity(self) -> str:
        return "error" if self.code.startswith("E-") else "warning"

    def to_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message, "path": self.path, "line": self.line}
