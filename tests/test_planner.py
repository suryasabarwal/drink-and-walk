from datetime import date

from dw import geo, planner, voice

STAY = {"lat": 42.8864, "lon": -78.8784, "name": "Test Hotel"}
FRI, SAT = date(2026, 12, 4), date(2026, 12, 5)


def build(places, **kw):
    args = dict(people=4, budget_pp=60, vibe="dive", live_music=False, late_night=False, free_only=False, deals={}, events=[])
    args.update(kw)
    return planner.build_plan(places, STAY, kw.pop("days", [FRI]) if "days" in kw else [FRI], args["people"], args["budget_pp"], args["vibe"], args["live_music"], args["late_night"], args["free_only"], args["deals"], args["events"])


def stops(plan, n=0):
    return plan["nights"][n]["stops"]


def test_no_pricey_places_ever_chosen(places):
    for vibe in ("dive", "chill", "lively"):
        p = build(places, vibe=vibe, live_music=True, late_night=True)
        for s in stops(p):
            assert s["place"]["price"]["tier"] != "pricey", s["place"]["name"]
            for alt in s["alternatives"]:
                assert alt["place"]["price"]["tier"] != "pricey"


def test_stops_are_in_time_order_and_close_together(places):
    p = build(places, live_music=True, late_night=True, budget_pp=200)
    mins = [s["minute"] for s in stops(p)]
    assert mins == sorted(mins)
    assert all(leg["min"] <= 25 for leg in p["nights"][0]["legs"])


def test_walking_legs_match_the_math(places):
    p = build(places)
    n = p["nights"][0]
    s0 = n["stops"][0]["place"]
    d = geo.haversine_m(STAY["lat"], STAY["lon"], s0["lat"], s0["lon"])
    assert n["legs"][0]["min"] == geo.walk_minutes(d)
    assert n["home"]["m"] >= 0


def test_live_music_stop_really_has_live_music(places):
    p = build(places, live_music=True)
    music = [s for s in stops(p) if s["slot"] == "music"]
    assert music and music[0]["place"]["live_music"]


def test_late_night_food_must_be_confirmed_open(places):
    p = build(places, late_night=True, budget_pp=200)
    late = [s for s in stops(p) if s["slot"] == "late"]
    assert late and late[0]["open"] is True
    for alt in late[0]["alternatives"]:
        assert alt["open"] is True


def test_free_filter_drops_ticketed_venues(places):
    p = build(places, free_only=True, live_music=True)
    for s in stops(p):
        assert not s["place"]["ticketed"]
        for a in s["alternatives"]:
            assert not a["place"]["ticketed"]


def test_closed_places_are_never_picked(places):
    # Corner Deli closes at 15:00 on weekdays, so it can't be the 6:30 pm dinner
    p = build(places)
    assert all(s["place"]["name"] != "Corner Deli and Sub" for s in stops(p))


def test_community_deal_lifts_a_place(places):
    target = next(x for x in places if x["name"] == "Rusty Anchor Tavern")
    p = build(places, deals={target["id"]: [{"id": "d1", "text": "$3 pints", "when": "Fri", "days_old": 2}]})
    names = [s["place"]["name"] for s in stops(p)]
    assert "Rusty Anchor Tavern" in names
    s = next(s for s in stops(p) if s["place"]["name"] == "Rusty Anchor Tavern")
    assert s["deals"][0]["text"] == "$3 pints"


def test_over_budget_trims_optional_stops_and_says_so(places):
    p = build(places, budget_pp=30, vibe="lively")
    n = p["nights"][0]
    assert not any(s["slot"] == "last" for s in n["stops"])
    assert any("Dropped" in t for t in n["tips"])


def test_budget_meter_states(places):
    rich = build(places, budget_pp=300)["nights"][0]["totals"]
    assert rich["state"] == "under"
    tight = build(places, budget_pp=5, vibe="dive")["nights"][0]["totals"]
    assert tight["state"] == "over" and "over" in tight["message"]


def test_second_night_prefers_new_places(places):
    p = planner.build_plan(places, STAY, [FRI, SAT], 4, 60, "dive", False, False, False, {}, [])
    a = {s["place"]["id"] for s in p["nights"][0]["stops"]}
    b = {s["place"]["id"] for s in p["nights"][1]["stops"]}
    assert not (a & b)


def test_thin_data_is_reported_honestly(places):
    p = planner.build_plan(places[:6], STAY, [FRI], 2, 60, "dive", True, True, False, {}, [])
    assert p["thin"] is True


def test_missing_live_music_gets_a_tip_not_a_fake_stop(places):
    no_music = [x for x in places if not x["live_music"]]
    p = planner.build_plan(no_music, STAY, [FRI], 2, 60, "dive", True, False, False, {}, [])
    assert voice.UI["no_live"] in p["nights"][0]["tips"]
    assert not any(s["slot"] == "music" for s in p["nights"][0]["stops"])


def test_empty_area_does_not_crash():
    p = planner.build_plan([], STAY, [FRI], 2, 60, "dive", True, True, False, {}, [])
    assert p["nights"][0]["stops"] == [] and p["thin"]


def test_swap_recompute_uses_new_place(places):
    p = build(places)
    s = p["nights"][0]["stops"][1]
    s["place"] = s["alternatives"][0]["place"]
    again = planner.finalize(planner.clean_plan({**p, "nights": p["nights"]}))
    assert again["nights"][0]["stops"][1]["place"]["id"] == s["place"]["id"]


def test_nearby_filters_and_sorts(places):
    out = planner.nearby(places, STAY["lat"], STAY["lon"], 4, 20 * 60, "drink", {})
    assert out and all(r["place"]["amenity"] in ("bar", "pub", "biergarten") for r in out)
    assert all(r["place"]["price"]["tier"] != "pricey" for r in out)
    late = planner.nearby(places, STAY["lat"], STAY["lon"], 4, 24 * 60 - 30 + 0, "late", {})
    assert all(r["open"] is True for r in late)


def test_alternatives_never_repeat_a_place_used_elsewhere_that_night(places):
    p = build(places, live_music=True, late_night=True, budget_pp=300)
    used = {s["place"]["id"] for s in stops(p)}
    for s in stops(p):
        assert not any(a["place"]["id"] in used for a in s["alternatives"])


def test_over_budget_drops_last_round_then_late_bite(places):
    from datetime import date, timedelta
    from dw import planner
    fri = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    stay = {"lat": 42.8864, "lon": -78.8784, "name": "Test Hotel"}
    roomy = planner.build_plan(places, stay, [fri], 2, 300, "dive", False, True, False, {}, [])["nights"][0]
    slots = [s["slot"] for s in roomy["stops"]]
    assert "late" in slots and "last" in slots
    full = roomy["totals"]["per_person"]
    last = next(s["cost"] for s in roomy["stops"] if s["slot"] == "last")
    tight = planner.build_plan(places, stay, [fri], 2, full - last - 1, "dive", False, True, False, {}, [])["nights"][0]
    kept = [s["slot"] for s in tight["stops"]]
    assert "last" not in kept and "late" not in kept
    assert tight["tips"][0].startswith("Dropped the last one")


def test_nearby_late_food_means_open_late_not_just_open_now():
    from dw import planner
    def place(i, hours):
        return {"id": f"n{i}", "name": f"P{i}", "lat": 0.0, "lon": 0.0, "amenity": "fast_food", "live_music": False,
                "ticketed": False, "no_cover": False, "price": {"tier": "cheap", "mid": 9, "low": 7, "high": 11}, "hours_raw": hours}
    ps = [place(1, "Mo-Su 11:00-20:00"), place(2, "Mo-Su 11:00-03:00"), place(3, None)]
    got = [r["place"]["id"] for r in planner.nearby(ps, 0.0, 0.0, 4, 18 * 60, "late", {})]
    assert got == ["n2"]
    after_midnight = [r["place"]["id"] for r in planner.nearby(ps, 0.0, 0.0, 5, 60, "late", {})]
    assert after_midnight == ["n2"]


def test_swap_options_never_repeat_a_name(places):
    from datetime import date, timedelta
    from dw import planner
    extra = []
    for i in range(3):
        base = next(p for p in places if p["amenity"] == "fast_food")
        extra.append(dict(base, id=f"n99{i}", name="Chain Burger", lat=base["lat"] + 0.0002 * (i + 1)))
    fri = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    n = planner.build_plan(places + extra, {"lat": 42.8864, "lon": -78.8784, "name": "x"}, [fri], 2, 200, "dive", False, False, False, {}, [])["nights"][0]
    for s in n["stops"]:
        names = [a["place"]["name"] for a in s["alternatives"]] + [s["place"]["name"]]
        assert len(names) == len(set(names))


def test_breather_costs_a_coffee_not_the_cafes_brunch_prices():
    from dw import planner
    cafe = {"amenity": "cafe", "price": {"low": 20, "high": 30, "mid": 25, "tier": "ok"}}
    bar = {"amenity": "bar", "price": {"low": 10, "high": 20, "mid": 15, "tier": "cheap"}}
    assert planner.stop_cost("breather", cafe) == (7, 5, 9)
    assert planner.stop_cost("breather", bar)[0] == 8  # one round
    assert planner.stop_cost("eat", cafe)[0] == 25


def test_breather_is_close_or_skipped():
    from datetime import date, timedelta
    from dw import planner
    def place(i, lat, amenity, name, lively=0.1):
        return {"id": f"n{i}", "name": name, "lat": lat, "lon": 0.0, "amenity": amenity, "live_music": False, "ticketed": False,
                "no_cover": False, "happy_hint": None, "website": "", "rating": 4.5, "rating_count": 50, "hours_week": [[[0, 1680]]] * 7,
                "vibe": {"dive": 0.2, "lively": lively, "chill": 0.1}, "price": {"tier": "cheap", "mid": 12, "low": 10, "high": 14}}
    ps = [place(1, 0.0, "fast_food", "Taco Spot"), place(2, 0.001, "bar", "Plain Bar"), place(3, 0.0015, "bar", "Second Plain Bar"),
          place(5, 0.0005, "bar", "Third Plain Bar"), place(4, 0.02, "cafe", "Far Away Cafe")]  # the cafe is 2 km out
    sat = date.today() + timedelta(days=(5 - date.today().weekday()) % 7 + 7)
    n = planner.build_plan(ps, {"lat": 0.0, "lon": 0.0, "name": "h"}, [sat], 2, 200, "chill", False, False, False, {}, [])["nights"][0]
    assert all(s["place"]["name"] != "Far Away Cafe" for s in n["stops"])
    assert any(s["slot"] == "last" for s in n["stops"])  # a plain bar counts as a quiet last round


def test_main_stop_picks_the_cheaper_bar_when_the_close_one_breaks_the_budget():
    from dw import planner
    def bar(i, lat, name, mid):
        return {"id": f"n{i}", "name": name, "lat": lat, "lon": 0.0, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "happy_hint": None, "website": "", "rating": 4.4, "rating_count": 100, "hours_week": [[[0, 1680]]] * 7,
                "vibe": {"dive": 0.5, "lively": 0.3, "chill": 0.3}, "price": {"tier": "ok" if mid > 20 else "cheap", "mid": mid, "low": mid - 5, "high": mid + 5}}
    ctx = {"free_only": False, "allow_pricey": False, "deals": {}, "used_other_nights": set(), "chains": set(), "budget": 50}
    night = {"weekday": 4, "used": set(), "spent": 40}
    main = {"key": "dive", "minute": 21 * 60, "role": "drink"}
    close_dear, near_cheap = bar(1, 0.0001, "Close But Dear", 25), bar(2, 0.004, "Few Blocks Cheaper", 12)
    s = lambda p: planner._score(p, main, (0.0, 0.0), "dive", ctx, night, 3500)[0]
    assert s(near_cheap) > s(close_dear)
    ctx["budget"] = 200  # plenty of room: the close one is fine
    assert s(close_dear) > s(near_cheap) - 0.5


def test_out_right_now_leaves_out_badly_rated_places():
    from dw import planner
    def bar(i, rating):
        return {"id": f"n{i}", "name": f"Bar {i}", "lat": 0.0, "lon": 0.0, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "rating": rating, "rating_count": 80, "hours_week": [[[0, 1680]]] * 7,
                "price": {"tier": "cheap", "mid": 12, "low": 10, "high": 14}}
    got = [r["place"]["id"] for r in planner.nearby([bar(1, 4.5), bar(2, 3.1)], 0.0, 0.0, 4, 21 * 60, "drink", {})]
    assert got == ["n1"]


def test_out_right_now_quips_rotate():
    from dw import planner
    def bar(i):
        return {"id": f"n{i}", "name": f"Bar {i}", "lat": 0.0, "lon": 0.0001 * i, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "hours_week": [[[0, 1680]]] * 7, "price": {"tier": "cheap", "mid": 12, "low": 10, "high": 14}}
    lines = [r["line"] for r in planner.nearby([bar(i) for i in range(4)], 0.0, 0.0, 4, 21 * 60, "drink", {})]
    assert len(set(lines)) == 4


def test_out_right_now_returns_everything_in_walking_distance_for_show_more():
    from dw import planner
    def bar(i, lon):
        return {"id": f"n{i}", "name": f"Bar {i}", "lat": 0.0, "lon": lon, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "hours_week": [[[0, 1680]]] * 7, "price": {"tier": "cheap", "mid": 12, "low": 10, "high": 14}}
    near = [bar(i, 0.0005 * i) for i in range(20)]      # all within about 1.1 km
    far = [bar(100, 0.02)]                               # about 2.2 km: past the 1.5 km limit
    got = planner.nearby(near + far, 0.0, 0.0, 4, 21 * 60, "drink", {})
    assert len(got) == 20 and all(r["walk"]["m"] <= 1500 for r in got)


def test_four_stars_is_the_floor_and_reach_is_one_and_a_half_km():
    from dw import planner
    def bar(i, rating, lon=0.0, count=80):
        return {"id": f"n{i}", "name": f"Bar {i}", "lat": 0.0, "lon": lon, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "rating": rating, "rating_count": count, "hours_week": [[[0, 1680]]] * 7,
                "price": {"tier": "ok", "mid": 18, "low": 15, "high": 22}}
    ps = [bar(1, 4.0), bar(2, 3.9), bar(3, 3.6, count=8), bar(4, 4.6, lon=0.0130), bar(5, 4.6, lon=0.0140)]  # 1.45 km and 1.56 km
    got = [r["place"]["id"] for r in planner.nearby(ps, 0.0, 0.0, 4, 21 * 60, "drink", {})]
    assert "n1" in got and "n2" not in got       # 4.0 in, 3.9 out
    assert "n3" in got                           # too few reviews to judge, so it stays
    assert "n4" in got and "n5" not in got       # inside 1.5 km in, past it out


def test_explain_lists_every_reason_a_place_was_left_out():
    from dw import planner
    def bar(i, rating, lon, hours=[[[0, 1680]]] * 7, tier="ok"):
        return {"id": f"n{i}", "name": f"Bar {i}", "lat": 0.0, "lon": lon, "amenity": "bar", "live_music": False, "ticketed": False,
                "no_cover": False, "rating": rating, "rating_count": 80, "hours_week": hours, "price": {"tier": tier, "mid": 18, "low": 15, "high": 22}}
    ps = [bar(1, 4.4, 0.001), bar(2, 3.8, 0.0125), bar(3, 4.2, 0.02, hours=[[] for _ in range(7)]), bar(4, 4.5, 0.002, tier="pricey")]
    skipped = []
    got = planner.nearby(ps, 0.0, 0.0, 4, 21 * 60, "drink", {}, skipped=skipped)
    assert [r["place"]["id"] for r in got] == ["n1"]
    why = {s["name"]: s["why"] for s in skipped}
    assert why == {"Bar 2": ["under_4_stars"], "Bar 3": ["too_far", "closed"], "Bar 4": ["pricey"]}
