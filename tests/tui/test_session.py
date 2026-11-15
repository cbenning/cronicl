import os

import pytest

from conftest import FAMILY, SITE, folder
from cronicl.core.recordedit import set_value
from cronicl.tui.session import DiskChanged, Session, Unreadable


def session_for(tmp_path, family=FAMILY, **kw):
    folder(tmp_path, family=family, **kw)
    return Session(tmp_path)


def test_staging_a_change_shows_in_the_diff_and_not_on_disk(tmp_path):
    session = session_for(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    assert session.changed
    diff = session.diff()
    assert len(diff) == 1 and diff[0].name == "family.yml"
    assert "-  sex: female" in diff[0].text and "+  sex: other" in diff[0].text
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_commit_writes_only_the_change_and_reloads(tmp_path):
    session = session_for(tmp_path)
    old = (tmp_path / "family.yml").read_bytes()
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    session.commit()
    new = (tmp_path / "family.yml").read_bytes()
    assert new == old.replace(b"  sex: female\n  birth: {date: 1815-12-10", b"  sex: other\n  birth: {date: 1815-12-10")
    assert not session.changed and session.family.tree.people["lovelace-ada"].sex == "U"


def test_commit_refuses_when_the_file_changed_on_disk_and_writes_nothing(tmp_path):
    session = session_for(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    (tmp_path / "family.yml").write_text(FAMILY + "\n# edited elsewhere\n", encoding="utf-8")
    before = (tmp_path / "family.yml").read_bytes()
    with pytest.raises(DiskChanged) as err:
        session.commit()
    assert err.value.names == ["family.yml"]
    assert (tmp_path / "family.yml").read_bytes() == before and session.changed


def test_a_same_size_edit_with_the_same_mtime_is_still_noticed(tmp_path):
    session = session_for(tmp_path)
    path = tmp_path / "family.yml"
    stamp = path.stat()
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    swapped = FAMILY.replace("George", "Georgf")
    path.write_text(swapped, encoding="utf-8")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(DiskChanged):
        session.commit()


def test_commit_is_atomic_when_the_replace_fails(tmp_path, monkeypatch):
    session = session_for(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("cronicl.tui.session.os.replace", boom)
    with pytest.raises(OSError):
        session.commit()
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY
    assert sorted(p.name for p in tmp_path.iterdir()) == ["family.yml", "site.yml"]  # no temp file left behind
    assert session.changed


def test_crlf_and_a_byte_order_mark_survive_a_write(tmp_path):
    raw = ("﻿" + FAMILY).replace("\n", "\r\n")
    (tmp_path / "site.yml").write_text(SITE, encoding="utf-8")
    (tmp_path / "family.yml").write_bytes(raw.encode("utf-8"))
    session = Session(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "death"), "1853"))
    session.commit()
    data = (tmp_path / "family.yml").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf") and b"\n" not in data.replace(b"\r\n", b"") and b"death: 1853" in data


def test_discard_drops_staged_changes_and_leaves_the_disk_alone(tmp_path):
    session = session_for(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    session.discard()
    assert not session.changed and session.staged["family.yml"] == FAMILY
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_the_family_and_its_issues_follow_the_staged_text(tmp_path):
    session = session_for(tmp_path)
    assert not [i for i in session.family.issues if i.code == "W-BAD-SEX"]
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "M"))
    assert [i.code for i in session.family.issues if i.code == "W-BAD-SEX"] == ["W-BAD-SEX"]


def test_unreadable_staged_text_is_refused_and_nothing_is_written(tmp_path):
    session = session_for(tmp_path)
    session.stage("family.yml", "a: [unclosed\n")
    with pytest.raises(Unreadable):
        session.commit()
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_a_folder_of_files_diffs_and_writes_each_changed_file_only(tmp_path):
    (tmp_path / "site.yml").write_text(SITE, encoding="utf-8")
    (tmp_path / "family").mkdir()
    (tmp_path / "family" / "one.yml").write_text("a: {name: {given: A}}\n", encoding="utf-8")
    (tmp_path / "family" / "two.yml").write_text("b: {name: {given: B}}\n", encoding="utf-8")
    session = Session(tmp_path)
    session.stage("family/two.yml", set_value(session.staged["family/two.yml"], ("b", "sex"), "male"))
    assert [d.name for d in session.diff()] == ["family/two.yml"]
    before = (tmp_path / "family" / "one.yml").stat().st_mtime_ns
    session.commit()
    assert "sex: male" in (tmp_path / "family" / "two.yml").read_text(encoding="utf-8")
    assert (tmp_path / "family" / "one.yml").stat().st_mtime_ns == before


def test_file_mode_is_kept(tmp_path):
    session = session_for(tmp_path)
    os.chmod(tmp_path / "family.yml", 0o640)
    session = Session(tmp_path)
    session.stage("family.yml", set_value(session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))
    session.commit()
    assert (os.stat(tmp_path / "family.yml").st_mode & 0o777) == 0o640
