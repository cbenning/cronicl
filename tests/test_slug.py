from famsite.slug import (
    FALLBACK_SLUG,
    MAX_ID_LEN,
    is_valid_id,
    natural_key,
    person_slug,
    slugify,
    unique_id,
)


def test_slugify_folds_accents_and_punctuation():
    assert slugify("Zoë O'Brien") == "zoe-o-brien"


def test_slugify_handles_special_letters():
    assert slugify("Straße") == "strasse"


def test_slugify_non_latin_becomes_empty():
    assert slugify("李") == ""


def test_person_slug_is_surname_first():
    assert person_slug("Bob", "Smith") == "smith-bob"


def test_person_slug_falls_back():
    assert person_slug("李", None) == FALLBACK_SLUG
    assert person_slug(None, None) == FALLBACK_SLUG


def test_person_slug_is_truncated_to_max_length():
    slug = person_slug("a" * 50, "b" * 50)
    assert len(slug) <= MAX_ID_LEN
    assert is_valid_id(slug)


def test_is_valid_id():
    assert is_valid_id("smith-bob")
    assert is_valid_id("bob2")
    for bad in ["", None, "Smith-Bob", "smith_bob", "-smith", "smith-", "a--b", "x" * 65]:
        assert not is_valid_id(bad)


def test_unique_id_adds_counter():
    assert unique_id("smith-bob", set()) == "smith-bob"
    assert unique_id("smith-bob", {"smith-bob"}) == "smith-bob-2"
    assert unique_id("smith-bob", {"smith-bob", "smith-bob-2"}) == "smith-bob-3"


def test_unique_id_respects_max_length():
    base = "x" * MAX_ID_LEN
    result = unique_id(base, {base})
    assert len(result) <= MAX_ID_LEN
    assert result.endswith("-2")


def test_natural_key_orders_numbers_numerically():
    assert sorted(["I10", "I2", "I1"], key=natural_key) == ["I1", "I2", "I10"]


def test_fold_slug_folds_accents_and_special_letters():
    from famsite.slug import fold_slug

    assert fold_slug("Zoë Müller") == "zoe-muller"
    assert fold_slug("Straße Ørsted") == "strasse-orsted"
    assert fold_slug("  --  ") == ""


def test_fold_slug_does_not_truncate_but_slugify_does():
    from famsite.slug import MAX_ID_LEN, fold_slug

    long_word = "a" * 70
    assert fold_slug(long_word) == long_word
    assert slugify(long_word) == "a" * MAX_ID_LEN
