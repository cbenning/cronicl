import pytest

from cronicl.check import check_tree
from cronicl.galleries import DEFAULT_LABEL, GalleryType, gallery_config, gallery_issues


def codes(issues):
    return sorted(i.code for i in issues)


def issues_for(gallery, make_tree=None, people=None):
    return gallery_issues({"gallery": gallery}, people or {})


GOOD = {"type": "fussel", "url": "https://x.example/photos/"}


@pytest.mark.parametrize("site", [{}, {"gallery": None}])
def test_not_configured_is_silent(site):
    assert gallery_issues(site, {}) == []
    assert gallery_config(site) is None


@pytest.mark.parametrize(
    "value", [{}, "https://x.example/", ["a"], {"url": "https://x.example/"}, {"type": "immich", "url": "https://x.example/"}]
)
def test_bad_type_is_an_error(value):
    assert codes(issues_for(value)) == ["E-GALLERY-TYPE"]
    assert gallery_config({"gallery": value}) is None


def test_unknown_type_message_lists_the_known_types():
    (issue,) = issues_for({"type": "immich", "url": "https://x.example/"})
    assert "fussel" in issue.message and issue.path == "site.yml"


@pytest.mark.parametrize(
    "url",
    [None, 5, "ftp://x.example/", "javascript:alert(1)", "https://", "https://x.example/?a=1", "https://x.example/#f", ""],
)
def test_bad_fussel_url_is_an_error(url):
    value = {"type": "fussel", **({} if url is None else {"url": url})}
    assert codes(issues_for(value)) == ["E-GALLERY-URL"]
    assert gallery_config({"gallery": value}) is None


@pytest.mark.parametrize(
    "url, expected",
    [("https://x.example/photos", "https://x.example/photos/"), ("https://x.example/photos//", "https://x.example/photos/"), ("http://x.example", "http://x.example/")],
)
def test_url_is_normalised_to_one_trailing_slash(url, expected):
    value = {"type": "fussel", "url": url}
    assert issues_for(value) == []
    assert gallery_config({"gallery": value}) == {"type": "fussel", "label": DEFAULT_LABEL, "url": expected, "portraits": True}


@pytest.mark.parametrize(
    "label, expected",
    [(None, "Photos"), ("  Family photos ", "Family photos"), ("x" * 100, "x" * 40), ("", "Photos"), ("   ", "Photos"), (5, "5")],
)
def test_label_is_trimmed_capped_and_defaulted(label, expected):
    value = {**GOOD, **({} if label is None else {"label": label})}
    assert gallery_config({"gallery": value})["label"] == expected


def test_unknown_key_is_a_warning_naming_the_valid_keys():
    (issue,) = issues_for({**GOOD, "colour": "red"})
    assert issue.code == "W-GALLERY-KEY"
    assert all(word in issue.message for word in ("colour", "url", "type", "label"))
    assert gallery_config({"gallery": {**GOOD, "colour": "red"}}) is not None


@pytest.mark.parametrize("key", ["api_key", "Token", "share_password", "client-secret"])
def test_secret_looking_keys_warn_that_they_are_published(key):
    issues = issues_for({**GOOD, key: "abc"})
    assert "W-GALLERY-SECRET" in codes(issues)
    assert "published" in next(i for i in issues if i.code == "W-GALLERY-SECRET").message


def test_gallery_id_without_a_usable_gallery_warns_once_per_person(make_tree):
    tree = make_tree([{"id": "a", "given": "A", "gallery_id": "a"}, {"id": "b", "given": "B"}])
    for site in ({}, {"gallery": {"type": "fussel"}}):
        found = [i for i in gallery_issues(site, tree.people) if i.code == "W-GALLERY-ID-UNUSED"]
        assert len(found) == 1 and "a" in found[0].message
    assert [i for i in gallery_issues({"gallery": GOOD}, tree.people) if i.code == "W-GALLERY-ID-UNUSED"] == []


def test_a_gallery_type_cannot_reuse_a_core_key():
    with pytest.raises(ValueError):
        GalleryType("x", keys=("label",), required=(), browser=True)


def test_check_tree_reports_gallery_issues(make_tree):
    tree = make_tree([{"id": "a", "given": "A", "surname": "B"}])
    tree.site = {"gallery": {"type": "nope"}}
    assert "E-GALLERY-TYPE" in codes(check_tree(tree))


@pytest.mark.parametrize(
    "url",
    ["https://[::1/", "https://ex\u2100mple.com/", "https://user:pw@host/p", "https://:pw@host/p", "https://host/p/?", "https://host/p/#",
     "https://host/a b/", "https://ho st/p/", "https://host/p\\q/", "https://host/p/\t"],
)
def test_urls_the_browser_would_reject_are_errors_and_never_crash(url):
    value = {"type": "fussel", "url": url}
    assert codes(issues_for(value)) == ["E-GALLERY-URL"]
    assert gallery_config({"gallery": value}) is None


def test_portraits_is_a_valid_key_and_defaults_to_true():
    assert issues_for({**GOOD, "portraits": True}) == []
    assert gallery_config({"gallery": GOOD})["portraits"] is True
    assert gallery_config({"gallery": {**GOOD, "portraits": False}})["portraits"] is False
    assert gallery_config({"gallery": {**GOOD, "portraits": True}})["portraits"] is True


@pytest.mark.parametrize("value", ["maybe", 2, [], None, ""])
def test_a_portraits_value_that_is_not_a_bool_warns_and_counts_as_true(value):
    gallery = {**GOOD, "portraits": value}
    assert codes(issues_for(gallery)) == ["W-GALLERY-PORTRAITS"]
    assert gallery_config({"gallery": gallery})["portraits"] is True


@pytest.mark.parametrize("value, expected", [("false", False), ("No", False), ("off", False), ("true", True), ("yes", True)])
def test_portraits_accepts_text_booleans(value, expected):
    gallery = {**GOOD, "portraits": value}
    assert issues_for(gallery) == []
    assert gallery_config({"gallery": gallery})["portraits"] is expected
