import pytest

from cronicl.media import resolve, safe_relative


@pytest.mark.parametrize("value, ok", [
    ("ann.jpg", True), ("scans/ann 1.jpg", True), ("", False), ("/etc/passwd", False),
    ("../ann.jpg", False), ("a/../../b.jpg", False), ("a\\b.jpg", False), ("a//b.jpg", False),
])
def test_safe_relative(value, ok):
    assert safe_relative(value) is ok


def test_resolve_refuses_a_symlink_out_of_media(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "ok.jpg").write_bytes(b"x")
    (tmp_path / "secret.jpg").write_bytes(b"s")
    (media / "link.jpg").symlink_to(tmp_path / "secret.jpg")
    assert resolve(media, "ok.jpg") == media / "ok.jpg"
    assert resolve(media, "link.jpg") is None and resolve(media, "nope.jpg") is None
