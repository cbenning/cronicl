from datetime import date

from cronicl.site.kin import build_kin
from cronicl.core.model import Event
from cronicl.core.relations import build_relations
from cronicl.site.render import build_site


def test_build_kin(make_tree):
    tree = make_tree([
        {"id": "a", "given": "Ann", "sex": "F", "spouse": ["b"]},
        {"id": "b", "given": "Bob", "sex": "M"},
        {"id": "c", "given": "Cy", "parents": ["a", "b"]},
    ])
    assert build_kin(tree, build_relations(tree)) == {"people": {
        "a": {"name": "Ann", "sex": "F", "parents": [], "partners": ["b"]},
        "b": {"name": "Bob", "sex": "M", "parents": [], "partners": ["a"]},
        "c": {"name": "Cy", "sex": "U", "parents": ["a", "b"], "partners": []},
    }}


def test_kin_json_holds_nothing_the_redacted_site_does_not(tmp_path, make_tree):
    tree = make_tree([
        {"id": "old", "given": "Old", "birth": Event(date="1800")},
        {"id": "secret-kid", "given": "Secret", "birth": Event(date="2000"), "parents": ["old"]},
    ])
    tree.site = {"privacy": {"living": "hidden", "id_salt": "s"}}
    build_site(tree, tmp_path, today=date(2026, 10, 10))
    text = (tmp_path / "kin.json").read_text(encoding="utf-8")
    assert "secret" not in text.lower() and '"old"' in text
