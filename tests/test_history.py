import os
import shutil
import subprocess

import pytest

from famsite.history import recent_changes


def git(root, *args, when):
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
        "PATH": os.environ["PATH"], "HOME": str(root),
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_recent_changes_newest_first_each_person_once(tmp_path, write):
    git(tmp_path, "init", "-q", when="2026-01-01T00:00:00Z")
    write(tmp_path, "people/a.md", "---\nname: A\n---\n")
    write(tmp_path, "people/b.md", "---\nname: B\n---\n")
    git(tmp_path, "add", "-A", when="2026-01-01T00:00:00Z")
    git(tmp_path, "commit", "-qm", "one", when="2026-01-01T12:00:00Z")
    write(tmp_path, "people/a.md", "---\nname: A2\n---\n")
    write(tmp_path, "people/gone.md", "---\nname: G\n---\n")
    git(tmp_path, "add", "-A", when="2026-02-02T00:00:00Z")
    git(tmp_path, "commit", "-qm", "two", when="2026-02-02T12:00:00Z")
    (tmp_path / "people/gone.md").unlink()
    assert recent_changes(tmp_path) == [{"id": "a", "date": "2026-02-02"}, {"id": "b", "date": "2026-01-01"}]
    assert recent_changes(tmp_path, limit=1) == [{"id": "a", "date": "2026-02-02"}]


def test_recent_changes_outside_git_is_empty(tmp_path):
    assert recent_changes(tmp_path) == []
