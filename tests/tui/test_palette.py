from conftest import FAMILY, drive, folder, highlight, option_texts, screen_name, texts
from test_editors import type_text


async def open_person(pilot, app, pid):
    app.open_person(pid)
    await pilot.pause()


def staged(app):
    return app.session.staged["family.yml"]


def test_the_palette_lists_only_fields_the_record_does_not_have(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await pilot.press("a")
        await pilot.pause()
        return screen_name(app), option_texts(app, "#fields")

    name, entries = drive(tmp_path, script)
    joined = "\n".join(entries)
    assert name == "PaletteScreen"
    assert "nickname" in joined and "bio" in joined and "portrait" in joined and "event: residence" in joined and "partner" in joined and "child" in joined
    labels = [e.split()[0] for e in entries if e.split()]
    for present in ("name.given", "name.surname", "sex", "parents", "death", "birth"):
        assert present not in labels, present
    assert "birth.place" not in labels  # Ada already has one; the parts she lacks (note, source) are offered
    assert "birth.note" in labels


def test_typing_narrows_the_palette_and_a_text_field_is_added_in_place(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "nick")
        first = option_texts(app, "#fields")[0]
        await pilot.press("enter")
        await pilot.pause()
        editor = screen_name(app)
        await type_text(pilot, "Enchantress")
        await pilot.press("enter")
        await pilot.pause()
        return first, editor, staged(app)

    first, editor, text = drive(tmp_path, script)
    assert "nickname" in first and editor == "TextEditor"
    assert "name: {given: Augusta Ada, surname: Lovelace, nickname: Enchantress}" in text


def test_a_death_can_be_added_to_someone_without_one(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "milbanke-annabella")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "death")
        await pilot.press("enter")
        await pilot.pause()
        editor = screen_name(app)
        await type_text(pilot, "1860")
        await pilot.press("enter")
        await pilot.pause()
        return editor, staged(app)

    editor, text = drive(tmp_path, script)
    assert editor == "DateEditor" and "  death: 1860\n" in text


def test_an_event_is_added_with_its_value_date_and_place(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "occupation")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Mathematician")  # the value
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "1840")  # the date
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")  # place: skipped
        await pilot.pause()
        return staged(app), screen_name(app)

    text, name = drive(tmp_path, script)
    assert "events:\n    - {type: occupation, date: 1840, value: Mathematician}" in text and name == "PersonScreen"


def test_parents_can_be_added_from_the_palette_until_there_are_two(tmp_path):
    folder(tmp_path, family=FAMILY + "\nlone:\n  name: {given: Lone}\n")

    async def script(pilot, app):
        await open_person(pilot, app, "lone")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "parents")
        await pilot.press("enter")
        await pilot.pause()
        await highlight(pilot, app, "George Byron", selector="#people")
        await pilot.press("enter")
        await pilot.pause()
        return staged(app)

    assert "parents: [byron-george]" in drive(tmp_path, script)


def test_a_field_of_your_own_asks_for_its_name_then_its_value(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "your own")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "x-nickname")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Enchantress")
        await pilot.press("enter")
        await pilot.pause()
        return staged(app)

    assert "  x-nickname: Enchantress\n" in drive(tmp_path, script)


def test_the_palette_on_a_couple_adds_events_to_the_couple_record(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "byron-george")
        await highlight(pilot, app, "Annabella Milbanke")
        await pilot.press("enter")  # expand
        await pilot.press("a")
        await pilot.pause()
        listed = option_texts(app, "#fields")
        await type_text(pilot, "residence")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter", "enter")  # no date, no place
        await pilot.pause()
        return listed, staged(app)

    listed, text = drive(tmp_path, script)
    assert any("note" in e for e in listed) and not any(e.strip().startswith("nickname") for e in listed)
    assert "type: residence" in text.split("byron-george + milbanke-annabella")[1]


def test_d_removes_a_line_after_a_confirmation(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await highlight(pilot, app, "- byron-george")
        await pilot.press("d")
        await pilot.pause()
        asked = texts(app)
        await pilot.press("n")
        await pilot.pause()
        unchanged = app.session.changed
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return asked, unchanged, staged(app)

    asked, unchanged, text = drive(tmp_path, script)
    assert "Remove" in asked and not unchanged
    assert "parents: [milbanke-annabella]" in text


def test_the_raw_pane_edits_one_record_and_refuses_broken_yaml(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "milbanke-annabella")
        await pilot.press("ctrl+e")
        await pilot.pause()
        from textual.widgets import TextArea

        area = app.screen.query_one("#area", TextArea)
        shown = area.text
        area.text = "milbanke-annabella:\n  name: [unclosed\n"
        await pilot.press("ctrl+s")
        await pilot.pause()
        still_open = screen_name(app), texts(app)
        area.text = "milbanke-annabella:\n  name: {given: Anne, surname: Milbanke}\n"
        await pilot.press("ctrl+s")
        await pilot.pause()
        return shown, still_open, screen_name(app), staged(app)

    shown, still_open, after, text = drive(tmp_path, script)
    assert shown.startswith("milbanke-annabella:") and "given: Annabella" in shown
    assert still_open[0] == "RawScreen" and "cannot" in still_open[1].lower()
    assert after == "PersonScreen" and "given: Anne," in text and "sex: female" not in text.split("milbanke-annabella:")[1].split("\n\n")[0]


# ---- review pass: parts of birth, death and events can be added after the fact
def test_a_place_can_be_added_to_a_bare_birth_date(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "milbanke-annabella")
        await pilot.press("a")
        await pilot.pause()
        listed = option_texts(app, "#fields")
        await type_text(pilot, "birth.place")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Elemore Hall")
        await pilot.press("enter")
        await pilot.pause()
        return listed, staged(app)

    listed, text = drive(tmp_path, script)
    assert any(e.startswith("birth.place") for e in listed)
    assert "birth: {date: 1792-05-17, place: Elemore Hall}" in text


def test_the_missing_parts_of_the_event_under_the_cursor_can_be_added(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "byron-george")
        await highlight(pilot, app, "Annabella Milbanke")
        await pilot.press("enter")  # expand the couple
        await highlight(pilot, app, "type: marriage")
        await pilot.press("a")
        await pilot.pause()
        listed = option_texts(app, "#fields")
        await type_text(pilot, "this event note")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Winter wedding")
        await pilot.press("ctrl+s")
        await pilot.pause()
        return listed, staged(app)

    listed, text = drive(tmp_path, script)
    assert any("this event: note" in e for e in listed) and not any("this event: date" in e for e in listed)
    assert "note: Winter wedding" in text.split("byron-george + milbanke-annabella")[1]


def test_a_birth_place_can_be_added_without_a_birth_date(tmp_path):
    folder(tmp_path, family=FAMILY + "\nplace-only:\n  name: {given: Place, surname: Only}\n")

    async def script(pilot, app):
        await open_person(pilot, app, "place-only")
        await pilot.press("a")
        await pilot.pause()
        listed = option_texts(app, "#fields")
        await type_text(pilot, "birth.place")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Leeds, England")
        await pilot.press("enter")
        await pilot.pause()
        return listed, staged(app)

    listed, text = drive(tmp_path, script)
    labels = [e.split()[0] for e in listed if e.split()]
    assert "birth" in labels and "birth.place" in labels and "death.place" in labels
    record = text.split("place-only:")[1]
    assert 'birth: {place: "Leeds, England"}' in record and "date" not in record


def test_a_death_place_alone_is_fine_too(tmp_path):
    folder(tmp_path, family=FAMILY + "\nplace-only:\n  name: {given: Place, surname: Only}\n")

    async def script(pilot, app):
        await open_person(pilot, app, "place-only")
        await pilot.press("a")
        await pilot.pause()
        await type_text(pilot, "death.place")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Hull")
        await pilot.press("enter")
        await pilot.pause()
        return staged(app), [i.code for i in app.session.family.issues]

    text, codes = drive(tmp_path, script)
    assert "death: {place: Hull}" in text.split("place-only:")[1]
    assert "W-DEATH-EMPTY" not in codes
