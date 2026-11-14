import json
from datetime import date

from cronicl.cli import main
from cronicl.model import Event, LifeEvent
from cronicl.search import search_people

TODAY = date(2026, 10, 10)


def p(pid, given, surname, **kw):
    return {"id": pid, "given": given, "surname": surname, **kw}


def sample(make_tree):
    return make_tree(
        [
            p("smith-john", "John", "Smith", birth=Event(date="1920", place="Halifax, NS"), death=Event(date="1990")),
            p("brown-mary", "Mary", "Brown", birth=Event(date="1925"), death=Event(date="2001")),
            p("smith-bob", "Bob", "Smith", birth=Event(date="1950", place="Vancouver, BC"),
              parents=["smith-john", "brown-mary"]),
            p("smith-bob-2", "Bob", "Smith", birth=Event(date="1975")),
            p("zoe-ng", "Zoë", "Ng", birth=Event(date="1990")),
            p("ashby-abby", "Abby", "Ashby"),
        ]
    )


def ids(hits):
    return [h.id for h in hits]


def test_exact_name_and_word_order_do_not_matter(make_tree):
    tree = sample(make_tree)
    assert set(ids(search_people(tree, "bob smith", today=TODAY))) == {"smith-bob", "smith-bob-2"}
    assert set(ids(search_people(tree, "smith bob", today=TODAY))) == {"smith-bob", "smith-bob-2"}


def test_case_and_accents_are_ignored(make_tree):
    assert ids(search_people(sample(make_tree), "ZOE", today=TODAY)) == ["zoe-ng"]


def test_close_spellings_match(make_tree):
    assert "smith-john" in ids(search_people(sample(make_tree), "smyth", today=TODAY))
    assert "ashby-abby" in ids(search_people(sample(make_tree), "asbhy", today=TODAY))


def test_prefix_and_substring_match(make_tree):
    assert "brown-mary" in ids(search_people(sample(make_tree), "mar", today=TODAY))
    assert "brown-mary" in ids(search_people(sample(make_tree), "rown", today=TODAY))


def test_years_and_places_are_searched(make_tree):
    tree = sample(make_tree)
    assert ids(search_people(tree, "1950", today=TODAY)) == ["smith-bob"]
    assert ids(search_people(tree, "vancouver", today=TODAY)) == ["smith-bob"]
    assert ids(search_people(tree, "smith 1975", today=TODAY)) == ["smith-bob-2"]


def test_every_query_word_must_match(make_tree):
    assert search_people(sample(make_tree), "bob zzzzzz", today=TODAY) == []


def test_exact_matches_rank_above_typos(make_tree):
    tree = make_tree([p("smyth-al", "Al", "Smyth"), p("smith-bo", "Bo", "Smith")])
    assert ids(search_people(tree, "smith", today=TODAY)) == ["smith-bo", "smyth-al"]


def test_limit(make_tree):
    assert len(search_people(sample(make_tree), "smith", today=TODAY, limit=2)) == 2


def test_hits_carry_context_for_telling_people_apart(make_tree):
    hit = next(h for h in search_people(sample(make_tree), "bob smith", today=TODAY) if h.id == "smith-bob")
    assert hit.name == "Bob Smith"
    assert hit.years == "b. 1950"
    assert hit.place == "Vancouver, BC"
    assert hit.parents == ["John Smith", "Mary Brown"]


def test_living_flag_follows_the_existing_rules_without_inference(make_tree):
    tree = sample(make_tree)
    john = search_people(tree, "john", today=TODAY)[0]
    bob = search_people(tree, "bob 1950", today=TODAY)[0]
    abby = search_people(tree, "abby", today=TODAY)[0]
    assert john.living is False  # has a death date
    assert bob.living is True  # born 1950, no death
    assert abby.living is True  # no dates at all: unknown, so flagged


def test_cli_text_json_and_exit_codes(tmp_path, write, capsys):
    write(tmp_path, "site.yml", "title: T\nschema_version: 1\n")
    write(tmp_path, "people/smith-bob.md", "---\nid: smith-bob\nname: Bob Smith\nbirth: 1950\n---\n")
    capsys.readouterr()
    assert main(["search", "bob", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "smith-bob" in out and "Bob Smith" in out
    assert main(["search", "nobodyatall", "--dir", str(tmp_path)]) == 1
    capsys.readouterr()
    assert main(["search", "bob", "--format", "json", "--dir", str(tmp_path)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["id"] == "smith-bob" and {"name", "years", "place", "parents", "living"} <= set(data[0])


def test_partnership_years_and_places_are_searchable(make_tree):
    from cronicl.model import Partnership

    tree = make_tree(
        [
            {"id": "a", "given": "Anna", "partnerships": [
                Partnership("b", type="marriage", start="1955", end="1971", place="Reno")
            ]},
            {"id": "b", "given": "Bert"},
        ]
    )
    for query in ("1971", "Reno"):
        found = [h.id for h in search_people(tree, query, today=date(2026, 10, 13))]
        assert "a" in found, query


def test_search_finds_event_values_and_places(make_tree):
    tree = make_tree([
        {"id": "a", "given": "Ann", "events": [LifeEvent(type="occupation", value="Carpenter"),
                                               LifeEvent(type="immigration", date="1952", place="Halifax")]},
        {"id": "b", "given": "Bob"},
    ])
    assert [h.id for h in search_people(tree, "carpenter", today=date(2026, 1, 1))] == ["a"]
    assert [h.id for h in search_people(tree, "halifax", today=date(2026, 1, 1))] == ["a"]
