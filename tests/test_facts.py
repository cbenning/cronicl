import pytest

from famsite.facts import fact_label, fact_text


@pytest.mark.parametrize("kind, value, text", [
    ("baptism", None, "baptised"), ("christening", None, "christened"), ("confirmation", None, "confirmed"),
    ("burial", None, "buried"), ("cremation", None, "cremated"),
    ("immigration", None, "immigrated"), ("emigration", None, "emigrated"), ("naturalization", None, "naturalised"),
    ("residence", None, "lived"), ("census", None, "recorded in a census"),
    ("occupation", "Carpenter", "worked as Carpenter"), ("occupation", None, "worked"),
    ("education", "Law", "studied Law"), ("education", None, "studied"),
    ("graduation", None, "graduated"), ("retirement", None, "retired"),
    ("will", None, "made a will"), ("probate", None, "estate went to probate"),
    ("religion", "Lutheran", "religion: Lutheran"), ("nationality", "German", "nationality: German"),
    ("moved-house", None, "moved house"), ("military-service", "RCAF", "military service: RCAF"),
])
def test_fact_text(kind, value, text):
    assert fact_text(kind, value) == text


def test_fact_label():
    assert [fact_label(k) for k in ("occupation", "moved-house", "")] == ["Occupation", "Moved house", "Event"]
