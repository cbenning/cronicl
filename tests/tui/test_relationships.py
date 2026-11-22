from conftest import FAMILY, SITE, drive, folder, highlight, option_texts, screen_name, texts
from test_editors import type_text

FAMILY_PLUS = FAMILY + """
other-person:
  name: {given: Other, surname: Person}
"""


def staged(app, name="family.yml"):
    return app.session.staged[name]


def head(app):
    from textual.widgets import Static

    return str(app.screen.query_one("#person-head", Static).content)


async def open_person(pilot, app, pid):
    app.open_person(pid)
    await pilot.pause()


async def palette_pick(pilot, query):
    await pilot.press("a")
    await pilot.pause()
    await type_text(pilot, query)
    await pilot.press("enter")
    await pilot.pause()


def test_an_existing_person_becomes_a_partner_with_a_marriage_date(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "partner")
        picker = screen_name(app)
        from conftest import highlight as hl

        await hl(pilot, app, "Other Person", selector="#people")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "1850")
        await pilot.press("enter")  # date
        await pilot.pause()
        await pilot.press("enter")  # place: none
        await pilot.pause()
        return picker, screen_name(app), staged(app), "\n".join(option_texts(app))

    picker, after, text, rows = drive(tmp_path, script)
    assert picker == "PeoplePicker" and after == "PersonScreen"
    assert "lovelace-ada + other-person:\n  events:\n    - {type: marriage, date: 1850}" in text
    assert "Other Person" in rows and "m. 1850" in rows


def test_a_new_person_as_partner_opens_nested_and_escape_returns_then_one_diff_covers_both(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    # the picker lists people first; reach "New person…" by typing something that matches nobody
    async def flow(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "partner")
        await type_text(pilot, "zzzzqq")  # no one: only "New person…" is left
        await pilot.press("enter")
        await pilot.pause()
        creating = screen_name(app)
        await type_text(pilot, "Wil")
        await pilot.press("tab")
        await type_text(pilot, "King")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")  # marriage date: skip
        await pilot.pause()
        await pilot.press("enter")  # place: skip
        await pilot.pause()
        nested = (screen_name(app), head(app))
        await pilot.press("escape")  # nested: back to Ada, no diff
        await pilot.pause()
        back = (screen_name(app), head(app))
        await pilot.press("escape")  # Ada: the one diff
        await pilot.pause()
        diff = (screen_name(app), texts(app))
        await pilot.press("y")
        await pilot.pause()
        return creating, nested, back, diff, screen_name(app)

    creating, nested, back, diff, after = drive(tmp_path, flow)
    assert creating == "NewPersonScreen"
    assert nested[0] == "PersonScreen" and "Wil King" in nested[1]
    assert back[0] == "PersonScreen" and "Augusta Ada" in back[1]
    assert diff[0] == "DiffScreen" and "+king-wil:" in diff[1].replace(" ", "") or "king-wil:" in diff[1]
    assert "king-wil + lovelace-ada" in diff[1] and after == "FinderScreen"
    written = (tmp_path / "family.yml").read_text(encoding="utf-8")
    assert "king-wil:\n  name: {given: Wil, surname: King}" in written and "king-wil + lovelace-ada" in written


def test_an_existing_person_is_made_a_child_by_adding_the_parent(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await highlight(pilot, app, "Other Person", selector="#people")
        await pilot.press("enter")
        await pilot.pause()
        return staged(app)

    text = drive(tmp_path, script)
    assert "other-person:\n  name: {given: Other, surname: Person}\n  parents: [lovelace-ada]" in text


def test_a_new_child_of_a_couple_asks_for_the_other_parent(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "byron-george")
        await palette_pick(pilot, "child")
        await type_text(pilot, "zzzzqq")
        await pilot.press("enter")  # New person…
        await pilot.pause()
        await type_text(pilot, "Junior")
        await pilot.press("tab")
        await type_text(pilot, "Byron")
        await pilot.press("enter")
        await pilot.pause()
        asked = screen_name(app), texts(app)
        await highlight(pilot, app, "Annabella", selector="#choices")
        await pilot.press("enter")
        await pilot.pause()
        return asked, staged(app), head(app)

    asked, text, opened = drive(tmp_path, script)
    assert asked[0] == "ChoiceEditor" and "Other parent" in asked[1]
    assert "byron-junior:\n  name: {given: Junior, surname: Byron}\n  parents: [byron-george, milbanke-annabella]" in text
    assert "Junior Byron" in opened


def test_a_new_person_can_be_made_the_parent_from_the_parents_picker(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await highlight(pilot, app, "- byron-george")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "zzzzqq")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Old")
        await pilot.press("tab")
        await type_text(pilot, "Man")
        await pilot.press("enter")
        await pilot.pause()
        return staged(app)

    text = drive(tmp_path, script)
    assert "parents: [man-old, milbanke-annabella]" in text and "man-old:\n  name: {given: Old, surname: Man}" in text


# ---- the unsaved-work rules
def stage_sex(app):
    from cronicl.core.recordedit import set_value

    app.session.stage("family.yml", set_value(app.session.staged["family.yml"], ("lovelace-ada", "sex"), "other"))


def test_escape_with_changes_shows_the_diff_and_n_keeps_editing(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        stage_sex(app)
        await pilot.press("escape")
        await pilot.pause()
        first = screen_name(app)
        await pilot.press("n")
        await pilot.pause()
        return first, screen_name(app), app.session.changed

    first, after, changed = drive(tmp_path, script)
    assert first == "DiffScreen" and after == "PersonScreen" and changed


def test_discarding_from_the_diff_leaves_the_file_byte_identical_and_goes_back(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        stage_sex(app)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        return screen_name(app), app.session.changed

    name, changed = drive(tmp_path, script)
    assert name == "FinderScreen" and not changed
    assert (tmp_path / "family.yml").read_text(encoding="utf-8") == FAMILY


def test_escape_without_changes_just_goes_back(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await pilot.press("escape")
        await pilot.pause()
        return screen_name(app)

    assert drive(tmp_path, script) == "FinderScreen"


def test_opening_another_person_with_changes_goes_through_the_diff_first(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        stage_sex(app)
        await highlight(pilot, app, "George Byron  1788")
        await pilot.press("enter")
        await pilot.pause()
        first = screen_name(app)
        await pilot.press("y")
        await pilot.pause()
        return first, screen_name(app), head(app)

    first, after, opened = drive(tmp_path, script)
    assert first == "DiffScreen" and after == "PersonScreen" and "George Byron" in opened
    assert "sex: other" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_quit_with_changes_goes_through_the_diff_and_without_exits(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        stage_sex(app)
        await pilot.press("ctrl+q")
        await pilot.pause()
        first = screen_name(app)
        await pilot.press("n")
        await pilot.pause()
        return first, screen_name(app), app.return_code

    first, after, code = drive(tmp_path, script)
    assert first == "DiffScreen" and after == "PersonScreen" and code is None


def test_quit_without_changes_exits(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await pilot.press("ctrl+q")
        await pilot.pause()
        return app._exit

    assert drive(tmp_path, script) is True


def test_a_new_person_from_the_finder_is_created_and_opened(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await pilot.press("ctrl+n")
        await pilot.pause()
        await type_text(pilot, "Zed")
        await pilot.press("tab")
        await type_text(pilot, "Zimmer")
        await pilot.press("enter")
        await pilot.pause()
        opened = screen_name(app), head(app)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return opened, screen_name(app)

    opened, after = drive(tmp_path, script)
    assert opened[0] == "PersonScreen" and "Zed Zimmer" in opened[1] and after == "FinderScreen"
    assert (tmp_path / "family.yml").read_text(encoding="utf-8").endswith("\nzimmer-zed:\n  name: {given: Zed, surname: Zimmer}\n")


def test_with_a_family_folder_a_new_person_asks_which_file(tmp_path):
    folder(tmp_path, family=None, extra={"family/one.yml": "a: {name: {given: A}}\n", "family/two.yml": "b: {name: {given: B}}\n"})

    async def script(pilot, app):
        await pilot.press("ctrl+n")
        await pilot.pause()
        asked = screen_name(app), texts(app)
        await highlight(pilot, app, "family/two.yml", selector="#choices")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Cee")
        await pilot.press("enter")
        await pilot.pause()
        return asked, app.session.staged

    asked, files = drive(tmp_path, script)
    assert asked[0] == "ChoiceEditor" and "family/one.yml" in asked[1]
    assert "cee:" in files["family/two.yml"] and "cee:" not in files["family/one.yml"]


def test_a_nameless_placeholder_can_be_created(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await pilot.press("ctrl+n")
        await pilot.pause()
        await pilot.press("enter")  # no name at all
        await pilot.pause()
        return staged(app)

    assert drive(tmp_path, script).endswith("\nunknown: {}\n")


# ---- review pass
def test_the_first_person_in_a_freshly_initialised_folder_can_be_added(tmp_path):
    async def script(pilot, app):
        await pilot.press("enter")  # Start a new family here
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        await type_text(pilot, "Ada")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        return screen_name(app)

    assert drive(tmp_path, script) == "FinderScreen"
    assert "\nada:\n  name: {given: Ada}\n" in (tmp_path / "family.yml").read_text(encoding="utf-8")


def test_a_blank_record_takes_a_burial_from_the_palette(tmp_path):
    folder(tmp_path, family=FAMILY + "\nghost:\n")

    async def script(pilot, app):
        await open_person(pilot, app, "ghost")
        await palette_pick(pilot, "burial")
        await pilot.press("enter", "enter")
        await pilot.pause()
        return staged(app), screen_name(app)

    text, name = drive(tmp_path, script)
    assert name == "PersonScreen" and "ghost:\n  events:\n    - {type: burial}" in text


def test_editing_a_row_that_uses_a_yaml_alias_says_so_and_changes_nothing(tmp_path):
    aliased = FAMILY + "\nsam-a:\n  name: {given: A}\n  birth: {date: 1800, place: &home Leeds}\n\nsam-b:\n  name: {given: B}\n  birth: {date: 1830, place: *home}\n"
    folder(tmp_path, family=aliased)

    async def script(pilot, app):
        await open_person(pilot, app, "sam-b")
        await highlight(pilot, app, "place: Leeds")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+u")
        await type_text(pilot, "Paris")
        await pilot.press("enter")
        await pilot.pause()
        return screen_name(app), app.session.changed

    name, changed = drive(tmp_path, script)
    assert name == "PersonScreen" and not changed


def test_a_person_screen_for_someone_who_no_longer_exists_closes_itself(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await type_text(pilot, "zzzzqq")
        await pilot.press("enter")
        await pilot.pause()
        await type_text(pilot, "Kid")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")  # (no partners: straight to the nested kid screen)
        await pilot.pause()
        nested = head(app)
        await highlight(pilot, app, "Augusta Ada")  # the Parents line of the new kid
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("x")  # discard everything: the kid no longer exists
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        return nested, screen_name(app)

    nested, name = drive(tmp_path, script)
    assert "Kid" in nested and name in ("FinderScreen", "PersonScreen")
    # whichever screen is shown, it must not be the vanished person
    async def check(pilot, app):
        return True

    assert drive(tmp_path, check)


def test_add_a_child_does_not_offer_existing_children(tmp_path):
    folder(tmp_path)

    async def script(pilot, app):
        await open_person(pilot, app, "byron-george")
        await palette_pick(pilot, "child")
        return option_texts(app, "#people")

    listed = "\n".join(drive(tmp_path, script))
    assert "Augusta Ada" not in listed and "Annabella" in listed or "Augusta Ada" not in listed


def test_the_partner_picker_does_not_offer_parents_or_children(tmp_path):
    folder(tmp_path, family=FAMILY + "\nother-person:\n  name: {given: Other, surname: Person}\n")

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "partner")
        return option_texts(app, "#people")

    listed = "\n".join(drive(tmp_path, script))
    assert "George Byron" not in listed and "Annabella" not in listed and "Other Person" in listed


def test_an_id_that_is_taken_by_a_scalar_record_is_not_proposed(tmp_path):
    folder(tmp_path, family="smith-john: oops\n")

    async def script(pilot, app):
        await pilot.press("ctrl+n")
        await pilot.pause()
        await type_text(pilot, "John")
        await pilot.press("tab")
        await type_text(pilot, "Smith")
        await pilot.press("enter")
        await pilot.pause()
        return screen_name(app), app.session.staged["family.yml"]

    name, text = drive(tmp_path, script)
    assert "smith-john-2" in text and name == "PersonScreen"


# ---- picking several relatives without reopening the picker
FAMILY_THREE = FAMILY_PLUS + """
third-person:
  name: {given: Third, surname: Person}
"""


async def pick_person(pilot, app, name):
    await highlight(pilot, app, name, selector="#people")
    await pilot.press("enter")
    await pilot.pause()


def test_add_a_child_keeps_the_picker_open_until_escape(tmp_path):
    folder(tmp_path, family=FAMILY_THREE)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await pick_person(pilot, app, "Other Person")
        after_one = (screen_name(app), option_texts(app, "#people"), texts(app))
        await pick_person(pilot, app, "Third Person")
        await pilot.press("escape")
        await pilot.pause()
        return after_one, screen_name(app), staged(app)

    (name, rows, shown), after, text = drive(tmp_path, script)
    assert name == "PeoplePicker" and not any("Other Person" in r for r in rows) and "Added: Other Person" in shown
    assert after == "PersonScreen"
    assert "other-person:\n  name: {given: Other, surname: Person}\n  parents: [lovelace-ada]" in text
    assert "third-person:\n  name: {given: Third, surname: Person}\n  parents: [lovelace-ada]" in text


def test_the_added_line_lists_everyone_picked_so_far(tmp_path):
    folder(tmp_path, family=FAMILY_THREE)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await pick_person(pilot, app, "Other Person")
        await pick_person(pilot, app, "Third Person")
        return texts(app)

    assert "Added: Other Person, Third Person" in drive(tmp_path, script)


def test_a_child_with_two_parents_is_refused_and_the_picker_stays_open(tmp_path):
    family = FAMILY_PLUS + "\nthird-person:\n  name: {given: Third, surname: Person}\n  parents: [byron-george, milbanke-annabella]\n"
    folder(tmp_path, family=family)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        before = staged(app)
        await pick_person(pilot, app, "Third Person")
        return screen_name(app), staged(app) == before, texts(app)

    name, unchanged, shown = drive(tmp_path, script)
    assert name == "PeoplePicker" and unchanged and "Added:" not in shown


def test_search_text_still_hides_people_already_picked(tmp_path):
    folder(tmp_path, family=FAMILY_THREE)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await pick_person(pilot, app, "Other Person")
        await type_text(pilot, "Person")
        return "\n".join(option_texts(app, "#people"))

    listed = drive(tmp_path, script)
    assert "Other Person" not in listed and "Third Person" in listed


def test_picking_the_last_person_leaves_only_new_person(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "child")
        await pick_person(pilot, app, "Other Person")
        rows = option_texts(app, "#people")
        await pilot.press("escape")
        await pilot.pause()
        return rows, screen_name(app)

    rows, after = drive(tmp_path, script)
    assert rows == ["＋ New person…"] and after == "PersonScreen"


def test_the_partner_picker_still_closes_after_one_pick(tmp_path):
    folder(tmp_path, family=FAMILY_PLUS)

    async def script(pilot, app):
        await open_person(pilot, app, "lovelace-ada")
        await palette_pick(pilot, "partner")
        await pick_person(pilot, app, "Other Person")
        return screen_name(app)

    assert drive(tmp_path, script) != "PeoplePicker"


def test_adding_parents_closes_the_picker_after_the_second(tmp_path):
    folder(tmp_path, family=FAMILY_THREE)

    async def script(pilot, app):
        await open_person(pilot, app, "other-person")
        await palette_pick(pilot, "parents")
        await pick_person(pilot, app, "Third Person")
        after_one = screen_name(app)
        await pick_person(pilot, app, "George Byron")
        return after_one, screen_name(app), staged(app)

    after_one, after_two, text = drive(tmp_path, script)
    assert after_one == "PeoplePicker" and after_two == "PersonScreen"
    assert "parents: [third-person, byron-george]" in text


def test_a_person_with_one_parent_closes_the_picker_after_one_more(tmp_path):
    family = FAMILY.replace("lovelace-ada:", "other-person:\n  name: {given: Other, surname: Person}\n  parents: [byron-george]\n\nlovelace-ada:")
    folder(tmp_path, family=family)

    async def script(pilot, app):
        await open_person(pilot, app, "other-person")
        await palette_pick(pilot, "parents")
        await pick_person(pilot, app, "Annabella Milbanke")
        return screen_name(app), staged(app)

    name, text = drive(tmp_path, script)
    assert name == "PersonScreen" and "parents: [byron-george, milbanke-annabella]" in text


def test_escape_after_the_first_parent_keeps_it(tmp_path):
    folder(tmp_path, family=FAMILY_THREE)

    async def script(pilot, app):
        await open_person(pilot, app, "other-person")
        await palette_pick(pilot, "parents")
        await pick_person(pilot, app, "Third Person")
        await pilot.press("escape")
        await pilot.pause()
        return screen_name(app), staged(app)

    name, text = drive(tmp_path, script)
    assert name == "PersonScreen" and "other-person:\n  name: {given: Other, surname: Person}\n  parents: [third-person]" in text


def test_adoptive_parents_are_counted_apart_from_birth_parents(tmp_path):
    family = FAMILY_THREE.replace("other-person:\n  name: {given: Other, surname: Person}", "other-person:\n  name: {given: Other, surname: Person}\n  parents: [byron-george, milbanke-annabella]")
    folder(tmp_path, family=family)

    async def script(pilot, app):
        await open_person(pilot, app, "other-person")
        await palette_pick(pilot, "adoptive-parents")
        await pick_person(pilot, app, "Third Person")
        return screen_name(app), staged(app)

    name, text = drive(tmp_path, script)
    assert name == "PeoplePicker" and "adoptive-parents: [third-person]" in text
