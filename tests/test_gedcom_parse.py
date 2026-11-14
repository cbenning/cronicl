import codecs

import pytest

from cronicl.gedcom import GedcomError, decode_gedcom, parse_nodes


def test_parse_builds_tree_and_joins_continuations():
    text = (
        "0 HEAD\n1 CHAR UTF-8\n"
        "0 @I1@ INDI\n1 NAME John /Smith/\n1 NOTE line one\n2 CONT line two\n2 CONC  continued\n"
        "0 TRLR\n"
    )
    nodes, issues = parse_nodes(text)
    assert [n.tag for n in nodes] == ["HEAD", "INDI", "TRLR"]
    indi = nodes[1]
    assert indi.xref == "@I1@"
    assert [c.tag for c in indi.children] == ["NAME", "NOTE"]
    assert indi.children[1].value == "line one\nline two continued"
    assert issues == []


def test_parse_handles_crlf_and_blank_lines():
    nodes, _ = parse_nodes("0 HEAD\r\n\r\n0 @I1@ INDI\r\n1 NAME A /B/\r\n")
    assert nodes[1].children[0].value == "A /B/"


def test_parse_tolerates_level_jumps_with_a_warning():
    nodes, issues = parse_nodes("0 @I1@ INDI\n1 BIRT\n3 DATE 1950\n")
    assert nodes[0].children[0].children[0].tag == "DATE"
    assert [i.code for i in issues] == ["W-GEDCOM-LEVEL"]


def test_parse_rejects_content_before_level_zero():
    with pytest.raises(GedcomError):
        parse_nodes("1 NAME A /B/\n")


def test_decode_utf8_bom():
    data = codecs.BOM_UTF8 + "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Zoë /Smith/\n".encode("utf-8")
    assert "Zoë" in decode_gedcom(data)


def test_decode_ansi_as_cp1252():
    data = b"0 HEAD\n1 CHAR ANSI\n0 @I1@ INDI\n1 NAME Ren\xe9 /Dup\xe9/\n"
    assert "René /Dupé/" in decode_gedcom(data)


def test_decode_utf16_with_bom():
    data = "0 HEAD\n1 CHAR UNICODE\n0 @I1@ INDI\n1 NAME Zoë /B/\n".encode("utf-16")
    assert "Zoë" in decode_gedcom(data)


def test_decode_rejects_ansel():
    with pytest.raises(GedcomError, match="ANSEL"):
        decode_gedcom(b"0 HEAD\n1 CHAR ANSEL\n")


def test_decode_rejects_invalid_utf8():
    with pytest.raises(GedcomError):
        decode_gedcom(b"0 HEAD\n1 CHAR UTF-8\n1 NAME \xff\xfe\n")
