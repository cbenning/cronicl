"""cronicl.core (the file format) never imports cronicl.site (the pages)."""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "cronicl"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.level


def test_core_does_not_import_site():
    offenders = []
    for path in sorted((PKG / "core").rglob("*.py")):
        for module, level in _imports(path):
            absolute = module if level == 0 else None
            if absolute and absolute.startswith("cronicl.site"):
                offenders.append((path.name, module))
            if level >= 2 and module.split(".")[0] == "site":
                offenders.append((path.name, "." * level + module))
            if level == 1 and module.split(".")[0] == "site":
                offenders.append((path.name, "." * level + module))
    assert offenders == []


def test_the_package_layout():
    names = sorted(p.name for p in PKG.iterdir() if p.name != "__pycache__")
    assert names == ["__init__.py", "checks.py", "checktext.py", "cli.py", "core", "site"]
    assert (PKG / "core" / "__init__.py").exists() and (PKG / "site" / "__init__.py").exists()
    assert (PKG / "site" / "templates").is_dir() and (PKG / "site" / "viewer").is_dir()
