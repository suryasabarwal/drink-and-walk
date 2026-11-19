from dw import places as P


def test_unnamed_and_irrelevant_elements_are_dropped(elements):
    names = [p["name"] for p in P.from_elements(elements)]
    assert all(names)
    assert len(names) == len(set(names))


def test_duplicates_are_merged_and_keep_the_richer_one(places):
    anchors = [p for p in places if p["name"] == "Rusty Anchor Tavern"]
    assert len(anchors) == 1
    assert anchors[0]["hours_raw"]


def test_fancy_places_are_marked_pricey(places):
    by = {p["name"]: p for p in places}
    assert by["Velvet Room Cocktail Lounge"]["price"]["tier"] == "pricey"
    assert by["Skyline Rooftop Bar"]["price"]["tier"] == "pricey"
    assert by["Cheap Slice Pizza"]["price"]["tier"] == "cheap"
    assert by["Fernwood Steakhouse"]["price"]["tier"] == "pricey"


def test_prices_are_always_labeled_estimates(places):
    assert all(p["price"]["estimate"] for p in places)


def test_happy_hour_only_from_real_tags(places):
    by = {p["name"]: p for p in places}
    assert "half price" in by["Happy Tag Bar"]["happy_hint"]
    assert sum(1 for p in places if p["happy_hint"]) == 1


def test_music_venue_is_ticketed_and_live(places):
    v = next(p for p in places if p["name"] == "Basement Sessions")
    assert v["ticketed"] and v["live_music"]


def test_open_state_unknown_when_no_hours(places):
    d = next(p for p in places if p["name"] == "Unlisted Hours Diner")
    assert P.open_state(d, 4, 18 * 60) is None
