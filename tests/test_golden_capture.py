"""The golden build the migration acceptance test compares against must stay in the repo, untouched."""
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden" / "legacy-build"


def test_golden_build_is_present_for_both_privacy_modes():
    for mode in ("full", "placeholder"):
        folder = GOLDEN / mode
        for name in ("index.json", "layout.json", "timeline.json", "kin.json"):
            assert (folder / name).is_file(), (mode, name)
        assert len(list((folder / "data" / "people").glob("*.json"))) >= 20, mode
        assert len(list((folder / "focus").glob("*.json"))) >= 20, mode


def test_the_legacy_fixture_covers_the_shapes_the_migration_must_handle():
    people = Path(__file__).parent / "fixtures" / "legacy" / "people"
    text = "\n".join(p.read_text(encoding="utf-8") for p in people.glob("*.md"))
    for needle in ("end_reason: divorce", "end_reason: annulment", "end_reason: separation", "end: unknown", "marriages:",
                   "children:", "spouse:", "gedcom_extra", "gallery_id", "living: false", "living: true", "portrait:", "~1850",
                   "type: engagement", "type: civil-union", "type: partnership", "cite:", "start: 1960"):
        assert needle in text or needle == "~1850" and "~1835" in text, needle
