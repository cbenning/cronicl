import pytest

from conftest import FAMILY, drive, folder, highlight, option_texts, screen_name, texts

FAMILY_PLUS = FAMILY + """
lovelace-anne:
  name: {given: Anne, surname: Lovelace}
  parents: [lovelace-ada]

other-person:
  name: {given: Other, surname: Person}
  bio: |
    One line.
"""


async def open_ada(pilot, app, text):
    app.open_person("lovelace-ada")
    await pilot.pause()
    await highlight(pilot, app, text)
    await pilot.press("enter")
    await pilot.pause()


async def type_text(pilot, text):
    for char in text:
        await pilot.press("space" if char == " " else {"-": "minus", ",": "comma", ".": "full_stop", ":": "colon"}.get(char, char))
    await pilot.pause()


def staged(app, name="family.yml"):
    return app.session.staged[name]


def test_a_text_field_edits_in_place_and_the_row_updates(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "given: Augusta Ada")
        modal = screen_name(app)
        await pilot.press("ctrl+u")
        await type_text(pilot, "Ada")
        await pilot.press("enter")
        await pilot.pause()
        return modal, screen_name(app), staged(app), option_texts(app)

    modal, after, text, rows = drive(tmp_path, script)
    assert modal == "TextEditor" and after == "PersonScreen"
    assert "name: {given: Ada, surname: Lovelace}" in text
    assert any("given: Ada" in r for r in rows)
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY  # nothing written yet


def test_escape_cancels_an_edit(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "given: Augusta Ada")
        await pilot.press("ctrl+u")
        await type_text(pilot, "zzz")
        await pilot.press("escape")
        await pilot.pause()
        return app.session.changed, screen_name(app)

    changed, name = drive(tmp_path, script)
    assert not changed and name == "PersonScreen"


def test_an_emptied_field_is_removed(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "surname: Lovelace")
        await pilot.press("ctrl+u", "enter")
        await pilot.pause()
        return staged(app)

    text = drive(tmp_path, script)
    assert "name: {given: Augusta Ada}" in text


def test_the_date_editor_reads_the_date_back_and_flags_nonsense(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "date: 1815-12-10")
        first = texts(app)
        await pilot.press("ctrl+u")
        await type_text(pilot, "1850-13")
        bad = texts(app)
        await pilot.press("ctrl+u", "f2")  # about
        await type_text(pilot, "1850")
        about = texts(app)
        await pilot.press("enter")
        await pilot.pause()
        return screen_name(app), first, bad, about, staged(app)

    modal_after, first, bad, about, text = drive(tmp_path, script)
    assert "10 December 1815" in first and "not a date" in bad and "about 1850" in about
    assert modal_after == "PersonScreen" and "date: ABT 1850" in text


def test_a_choice_field_offers_the_four_words(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "sex: female")
        shown = texts(app)
        await highlight(pilot, app, "other", selector="#choices")
        await pilot.press("enter")
        await pilot.pause()
        return shown, staged(app)

    shown, text = drive(tmp_path, script)
    assert all(word in shown for word in ("male", "female", "unknown", "other")) and "sex: other" in text


def test_a_place_is_suggested_from_places_already_in_the_file_but_free_text_works(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "place: London, England")
        await pilot.press("ctrl+u")
        await type_text(pilot, "seah")
        suggested = option_texts(app, "#choices")
        await pilot.press("ctrl+u")
        await type_text(pilot, "Paris, France")
        await pilot.press("up")
        await pilot.press("enter")
        await pilot.pause()
        return suggested, staged(app)

    suggested, text = drive(tmp_path, script)
    assert any("Seaham, England" in s for s in suggested) and any(s.startswith('Use "seah"') for s in suggested)
    assert "Paris, France" in text


def test_a_parent_is_chosen_from_a_picker_that_skips_self_the_other_parent_and_descendants(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        await open_ada(pilot, app, "- byron-george")
        listed = option_texts(app, "#people")
        await highlight(pilot, app, "Other Person", selector="#people")
        await pilot.press("enter")
        await pilot.pause()
        return listed, staged(app)

    listed, text = drive(tmp_path, script)
    joined = "\n".join(listed)
    assert "Other Person" in joined and "George Byron" in joined and "New person" in joined
    assert "Augusta Ada" not in joined and "Anne Lovelace" not in joined and "Annabella" not in joined
    assert "parents: [other-person, milbanke-annabella]" in text


def test_a_long_text_field_uses_a_text_area_and_ctrl_s_accepts(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        app.open_person("other-person")
        await pilot.pause()
        await highlight(pilot, app, "bio:")
        await pilot.press("enter")
        await pilot.pause()
        name = screen_name(app)
        await pilot.press("ctrl+a" if False else "end")
        await type_text(pilot, "!")
        await pilot.press("ctrl+s")
        await pilot.pause()
        return name, staged(app)

    name, text = drive(tmp_path, script)
    assert name == "LongTextEditor" and "One line.!" in text


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_editors_fit_small_and_large_terminals(tmp_path, size):
    folder(tmp_path)

    async def script(pilot, app):
        await open_ada(pilot, app, "date: 1815-12-10")
        return screen_name(app), texts(app)

    name, shown = drive(tmp_path, script, size)
    assert name == "DateEditor" and "birth" in shown.lower()
