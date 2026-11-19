"""Google Places (New) adapter. Responses below are synthetic, shaped like the documented API.
The place names are made up."""
from datetime import date, timedelta

import pytest
import requests

from dw import config, planner
from dw.places import open_state
from dw.sources import SourceDown, google_places as G

C = (42.8864, -78.8784)


def gp(i, name, primary, types, level=None, rng=None, hours=None, **extra):
    d = {"id": f"ChIJfake{i:04d}", "displayName": {"text": name}, "primaryType": primary, "types": types,
         "location": {"latitude": C[0] + i * 0.0006, "longitude": C[1]}, "businessStatus": "OPERATIONAL",
         "shortFormattedAddress": f"{i} Test St", "googleMapsUri": f"https://maps.google.com/?cid={i}", "rating": 4.3, "userRatingCount": 120}
    if level: d["priceLevel"] = level
    if rng: d["priceRange"] = {"startPrice": {"currencyCode": "USD", "units": str(rng[0])}, "endPrice": {"currencyCode": "USD", "units": str(rng[1])}}
    if hours: d["regularOpeningHours"] = {"periods": hours}
    d.update(extra)
    return d


def every_day(oh, om, ch, cm, next_day):
    return [{"open": {"day": d, "hour": oh, "minute": om}, "close": {"day": (d + 1) % 7 if next_day else d, "hour": ch, "minute": cm}} for d in range(7)]


LATE = every_day(16, 0, 2, 0, True)
DINNER = every_day(11, 0, 22, 0, False)
FAKE = {
    "bars_popular": [
        gp(1, "Lamp Post Pub", "pub", ["pub", "bar"], "PRICE_LEVEL_INEXPENSIVE", hours=LATE, servesBeer=True, liveMusic=True),
        gp(2, "Gilded Cocktail Parlor", "cocktail_bar", ["cocktail_bar", "bar"], "PRICE_LEVEL_EXPENSIVE", hours=LATE),
        gp(3, "Corner Taps", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", hours=LATE, servesBeer=True),
    ],
    "bars_close": [gp(10, "Grand Lobby Hotel", "hotel", ["hotel", "lodging", "bar"]),
                   gp(11, "Oak Barrel Room", "bar", ["bar"], "PRICE_LEVEL_MODERATE", (20, 30), hours=LATE, servesBeer=True),
                   gp(12, "Wide Range Saloon", "bar", ["bar"], "PRICE_LEVEL_MODERATE", (10, 50), hours=LATE, servesBeer=True),
                   gp(13, "Ten Dollar Taps", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", (10, 20), hours=LATE, servesBeer=True),gp(4, "Blue Door Bar", "bar", ["bar"], "PRICE_LEVEL_MODERATE", hours=LATE, servesBeer=True, rating=2.9, userRatingCount=80),
                   gp(9, "Closed Forever Tavern", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", hours=LATE, businessStatus="CLOSED_PERMANENTLY")],
    "cheap_food": [gp(5, "Slice Window", "pizza_restaurant", ["pizza_restaurant", "restaurant"], "PRICE_LEVEL_INEXPENSIVE", (10, 20), hours=every_day(11, 0, 3, 0, True))],
    "restaurants": [gp(6, "Noodle Counter", "ramen_restaurant", ["ramen_restaurant", "restaurant"], "PRICE_LEVEL_INEXPENSIVE", hours=DINNER),
                    gp(7, "Prime Cut House", "steak_house", ["steak_house", "restaurant"], "PRICE_LEVEL_VERY_EXPENSIVE", hours=DINNER)],
    "live": [gp(8, "Back Room Stage Bar", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", hours=LATE, liveMusic=True, servesBeer=True)],
    "late": [],
}


class Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "test-key")
    calls = []
    def post(url, json=None, timeout=None, headers=None):
        assert headers["X-Goog-Api-Key"] == "test-key" and "places.priceLevel" in headers["X-Goog-FieldMask"]
        kind = next((k for k, v in G.NEARBY_SEARCHES.items() if json.get("includedTypes") == v["includedTypes"] and json.get("rankPreference") == v["rankPreference"]), None)
        kind = kind or next(k for k, q in G.TEXT_SEARCHES.items() if json.get("textQuery") == q)
        calls.append(kind)
        return Resp(200, {"places": FAKE[kind]})
    monkeypatch.setattr(G.session, "post", post)
    return calls


def by_name(places):
    return {p["name"]: p for p in places}


def test_normalize_prices_hours_and_flags(google):
    places, meta = G.places_near(*C, 1500)
    p = by_name(places)
    assert meta["source"] == "google" and "Closed Forever Tavern" not in p
    assert p["Gilded Cocktail Parlor"]["price"]["tier"] == "pricey" and p["Prime Cut House"]["price"]["tier"] == "pricey"
    assert p["Lamp Post Pub"]["price"]["tier"] == "cheap" and p["Lamp Post Pub"]["amenity"] == "pub" and p["Lamp Post Pub"]["live_music"]
    s = p["Slice Window"]
    assert (s["price"]["low"], s["price"]["high"], s["price"]["mid"]) == (10, 20, 15) and "$10 to $20" in s["price"]["basis"]
    assert s["amenity"] == "restaurant" and s["cuisine"] == "pizza" and s["gmaps"].startswith("https://maps.google.com/")
    assert all(x["price"]["estimate"] for x in places) and all(x["happy_hint"] is None for x in places)
    assert "Grand Lobby Hotel" not in p
    assert p["Oak Barrel Room"]["price"]["tier"] == "pricey" and p["Wide Range Saloon"]["price"]["tier"] == "pricey"
    assert p["Ten Dollar Taps"]["price"]["tier"] == "cheap"


def test_google_hours_overnight_and_closed():
    fri_late = {"hours_week": G._week({"periods": [{"open": {"day": 5, "hour": 18, "minute": 0}, "close": {"day": 6, "hour": 2, "minute": 0}}]})}
    assert open_state(fri_late, 4, 19 * 60) is True          # Fri 7pm (Google day 5 = Friday)
    assert open_state(fri_late, 4, 24 * 60 + 30, span=60) is True   # 12:30am into Saturday
    assert open_state(fri_late, 4, 25 * 60 + 30, span=60) is False  # 1:30am, closes at 2
    assert open_state(fri_late, 3, 19 * 60) is False         # Thursday closed
    always = {"hours_week": G._week({"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]})}
    assert open_state(always, 2, 4 * 60) is True
    assert open_state({"hours_week": None, "hours_raw": None}, 2, 600) is None


def test_live_and_late_searches_only_when_asked_and_cached(google):
    G.places_near(*C, 1500)
    assert sorted(google) == sorted(G.NEARBY_SEARCHES)
    google.clear()
    G.places_near(C[0] - 0.0003, C[1], 1500, want_live=True)
    assert google == ["live"]  # the four core searches came from the cache


def test_plan_uses_google_and_skips_pricey_and_badly_rated(google):
    fri = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    places, _ = G.places_near(*C, 1500, want_live=True, want_late=True)
    plan = planner.build_plan(places, {"lat": C[0], "lon": C[1], "name": "x"}, [fri], 4, 80, "dive", True, True, False, {}, [])
    names = [s["place"]["name"] for s in plan["nights"][0]["stops"]]
    assert "Gilded Cocktail Parlor" not in names and "Prime Cut House" not in names
    assert names and len(set(names)) == len(names)
    music = next(s for s in plan["nights"][0]["stops"] if s["slot"] == "music")
    assert music["place"]["live_music"]
    late = next((s for s in plan["nights"][0]["stops"] if s["slot"] == "late"), None)
    assert late is None or late["open"] is True
    assert planner.rating_bonus(by_name(places)["Blue Door Bar"]) < 0


def test_google_failure_falls_back_to_open_map(monkeypatch, client):
    import app as appmod
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "bad")
    monkeypatch.setattr(G.session, "post", lambda *a, **k: Resp(403, {"error": {"status": "PERMISSION_DENIED"}}))
    places, meta = appmod.get_places(*C, 1500)
    assert places and meta["fallback_from"].startswith("google answered 403")


def test_google_daily_budget(monkeypatch, google):
    monkeypatch.setattr(config, "GOOGLE_DAILY_LIMIT", 0)
    with pytest.raises(SourceDown):
        G.places_near(50.0, 50.0, 1500)
    assert google == []


def test_google_place_ids_work_for_deals_and_recompute(client):
    ok = client.post("/api/deals", json={"place_id": "g:ChIJfake0001", "place_name": "Lamp Post Pub", "text": "$4 pints all night", "when": "Mon"})
    assert ok.status_code == 201
    from dw.planner import clean_place
    c = clean_place({"id": "g:ChIJfake0001", "name": "x", "gmaps": "https://maps.google.com/?cid=1"})
    assert c["id"] == "g:ChIJfake0001" and c["gmaps"]
    assert clean_place({"id": "g:../../etc", "gmaps": "javascript:x"})["id"] == "n0"
