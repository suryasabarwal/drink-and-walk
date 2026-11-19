"""Local currency end to end. Google responses below are synthetic, shaped like the documented
Places API (New), with made-up place names."""
from datetime import date, datetime, timedelta, timezone

import pytest

from dw import config, export, money, planner
from dw.places import estimate_price
from dw.sources import google_places as G

from test_voice import check

C = (42.8864, -78.8784)
FRI = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
LATE = [{"open": {"day": d, "hour": 12, "minute": 0}, "close": {"day": (d + 1) % 7, "hour": 2, "minute": 0}} for d in range(7)]


def gp(i, name, primary, types, level=None, rng=None, cur="EUR", **extra):
    d = {"id": f"ChIJeuro{i:04d}", "displayName": {"text": name}, "primaryType": primary, "types": types,
         "location": {"latitude": C[0] + i * 0.0005, "longitude": C[1]}, "businessStatus": "OPERATIONAL",
         "shortFormattedAddress": f"Rua Teste {i}", "googleMapsUri": f"https://maps.google.com/?cid=9{i}",
         "rating": 4.4, "userRatingCount": 200, "regularOpeningHours": {"periods": LATE}}
    if level:
        d["priceLevel"] = level
    if rng:
        d["priceRange"] = {"startPrice": {"currencyCode": cur, "units": str(rng[0])},
                           "endPrice": {"currencyCode": cur, "units": str(rng[1])}}
    d.update(extra)
    return d


EURO = {
    "bars_popular": [
        gp(1, "Little Tile Tavern", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", (5, 10), servesBeer=True),
        gp(2, "Harbor Steps Bar", "bar", ["bar"], "PRICE_LEVEL_MODERATE", (10, 20), servesBeer=True, liveMusic=True),
        gp(3, "Upper Terrace Pub", "pub", ["pub", "bar"], "PRICE_LEVEL_MODERATE", (16, 25), servesBeer=True),
    ],
    "bars_close": [
        gp(4, "No Range Bar", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", servesBeer=True),
        gp(5, "Plain Corner Bar", "bar", ["bar"], servesBeer=True),
        gp(6, "Odd Coin Bar", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", (50, 90), cur="XQQ", servesBeer=True),
    ],
    "cheap_food": [gp(7, "Grill Window", "sandwich_shop", ["sandwich_shop", "restaurant"], "PRICE_LEVEL_INEXPENSIVE", (5, 10))],
    "restaurants": [gp(8, "Blue Plate Kitchen", "restaurant", ["restaurant"], "PRICE_LEVEL_MODERATE", (10, 20)),
                    gp(9, "Long Table House", "restaurant", ["restaurant"], "PRICE_LEVEL_MODERATE", (15, 30))],
    "live": [], "late": [],
}


class Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


@pytest.fixture
def euro_google(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "test-key")

    def post(url, json=None, timeout=None, headers=None):
        kind = next((k for k, v in G.NEARBY_SEARCHES.items() if json.get("includedTypes") == v["includedTypes"] and json.get("rankPreference") == v["rankPreference"]), None)
        kind = kind or next(k for k, q in G.TEXT_SEARCHES.items() if json.get("textQuery") == q)
        return Resp(200, {"places": EURO[kind]})
    monkeypatch.setattr(G.session, "post", post)


def by_name(places):
    return {p["name"]: p for p in places}


# ---- the Google adapter keeps any currency ---------------------------------------------------

def test_google_range_in_euros_is_kept_with_its_currency(euro_google):
    places, _ = G.places_near(*C, 1500)
    p = by_name(places)
    t = p["Harbor Steps Bar"]["price"]
    assert (t["low"], t["high"], t["mid"], t["currency"]) == (10, 20, 15, "EUR") and not t["guess"]
    assert "€10 to €20" in t["basis"] and "$" not in t["basis"]
    assert p["Little Tile Tavern"]["price"]["tier"] == "cheap"
    # Pricey thresholds are scaled: a drinks stop starting at €16 is pricey, like $20 in the US.
    assert p["Upper Terrace Pub"]["price"]["tier"] == "pricey"
    assert p["Long Table House"]["price"]["tier"] == "ok"  # €15 to €30 for dinner is not pricey


def test_unknown_currency_falls_back_to_price_level(euro_google):
    places, _ = G.places_near(*C, 1500)
    odd = by_name(places)["Odd Coin Bar"]["price"]
    assert odd["tier"] == "cheap" and odd["guess"] and odd["currency"] == "USD"
    assert odd["mid"] < 50


def test_no_range_stays_a_usd_guess_until_localized(euro_google):
    places, _ = G.places_near(*C, 1500)
    plain = by_name(places)["Plain Corner Bar"]["price"]
    assert plain["guess"] and plain["currency"] == "USD"
    local = money.localize_price(plain, "EUR", "PT")
    assert local["currency"] == "EUR" and local["mid"] == round(plain["mid"] * 0.55)
    assert plain["currency"] == "USD"  # the original is not changed


def test_usd_range_still_works_for_us_places():
    g = gp(1, "Test Taps", "bar", ["bar"], "PRICE_LEVEL_INEXPENSIVE", (10, 20), cur="USD", servesBeer=True)
    p = G.normalize(g)["price"]
    assert (p["low"], p["high"], p["currency"], p["tier"]) == (10, 20, "USD", "cheap") and "$10 to $20" in p["basis"]
    assert money.localize_price(p, "USD", "US") == p


# ---- money helpers ---------------------------------------------------------------------------

def test_formatting_and_budget_ranges():
    assert money.fmt(14, "EUR") == "€14" and money.fmt(1250, "JPY") == "¥1,250" and money.fmt(40, "USD") == "$40"
    assert money.fmt(120, "SEK") == "120 kr"
    assert money.currency_for("pt") == "EUR" and money.currency_for("US") == "USD" and money.currency_for("") == "USD"
    assert money.budget_ui("USD") == {"min": 20, "max": 150, "step": 5, "default": 50, "chips": [30, 50, 75, 100]}
    eur = money.budget_ui("EUR")
    assert eur["min"] < eur["default"] < eur["max"] and all(c % eur["step"] == 0 for c in eur["chips"])
    jpy = money.budget_ui("JPY")
    assert jpy["step"] >= 100 and jpy["default"] > 1000


def test_estimates_scale_per_country_and_round_sensibly():
    usd = estimate_price("bar", "Some Bar", {})
    pt = money.localize_price(usd, "EUR", "PT")
    ie = money.localize_price(usd, "EUR", "IE")
    assert pt["mid"] < ie["mid"] and pt["currency"] == ie["currency"] == "EUR"
    jp = money.localize_price(usd, "JPY", "JP")
    assert jp["mid"] % 10 == 0 and jp["mid"] > 500 and jp["low"] <= jp["mid"] <= jp["high"]


def test_a_range_in_another_currency_is_converted():
    gbp = {"low": 10, "high": 20, "mid": 15, "tier": "ok", "basis": "x", "currency": "GBP", "guess": False}
    out = money.localize_price(gbp, "EUR", "IE")
    assert out["currency"] == "EUR" and out["mid"] == 16 and "£10 to £20" in out["basis"] and "€" in out["basis"]


# ---- Lisbon end to end -----------------------------------------------------------------------

LISBON = {"city": {"name": "Lisbon", "country": "PT"}, "start": FRI.isoformat(), "end": FRI.isoformat(), "people": 3,
          "budget_pp": 40, "stay": {"lat": C[0], "lon": C[1], "name": "Test Guesthouse"}, "vibe": "dive",
          "live_music": False, "late_night": False, "free_only": False}


def test_lisbon_plan_is_in_euros_on_screen_in_text_and_calendar(client, euro_google):
    j = client.post("/api/plan", json=LISBON).json
    assert j["currency"] == "EUR" and j["nights"][0]["stops"]
    for s in j["nights"][0]["stops"] + [a for s in j["nights"][0]["stops"] for a in s["alternatives"]]:
        assert s["place"]["price"]["currency"] == "EUR"
    by = {s["place"]["name"]: s["place"]["price"] for s in j["nights"][0]["stops"]}
    assert by["No Range Bar"]["guess"] and by["No Range Bar"]["mid"] < 12  # a US guess, scaled to Lisbon prices
    t = j["nights"][0]["totals"]
    assert "$" not in t["message"]
    assert "€" in j["text"] and "$" not in j["text"]
    assert f"about €{t['per_person']} each (€{t['group']} total)" in j["text"]

    slim = {**j, "nights": [{**n, "stops": [{k: v for k, v in s.items() if k != "alternatives"} for s in n["stops"]]} for n in j["nights"]]}
    r = client.post("/api/recompute", json={"plan": slim}).json
    assert "€" in r["text"] and "$" not in r["text"] and "$" not in r["nights"][0]["totals"]["message"]
    ics = client.post("/api/ics", json={"plan": slim}).data.decode()
    assert "About €" in ics and "$" not in ics


def test_lisbon_budget_is_checked_in_euros(client, euro_google):
    assert client.post("/api/plan", json={**LISBON, "budget_pp": 600}).status_code == 400
    tight = client.post("/api/plan", json={**LISBON, "budget_pp": 5}).json
    tips = " ".join(tight["nights"][0]["tips"])
    assert "€5 limit" in tips and "$" not in tips
    check(tips, "tips")
    check(tight["nights"][0]["totals"]["message"], "meter")


def test_yen_budget_is_accepted(client):
    body = {**LISBON, "city": {"name": "Testshi", "country": "JP"}, "budget_pp": 4500}
    j = client.post("/api/plan", json=body).json
    assert j["currency"] == "JPY" and "¥" in j["text"] and "$" not in j["text"]
    assert all(s["cost"] >= 100 for s in j["nights"][0]["stops"])


def test_us_plan_is_unchanged(client):
    body = {**LISBON, "city": {"name": "Testville", "country": "US"}, "budget_pp": 60}
    j = client.post("/api/plan", json=body).json
    assert j["currency"] == "USD" and "$" in j["text"] and "€" not in j["text"]
    assert all(s["place"]["price"]["currency"] == "USD" for s in j["nights"][0]["stops"])


def test_nearby_uses_the_country_or_googles_currency(client, euro_google):
    q = f"/api/nearby?lat={C[0]}&lon={C[1]}&day=4&minute=1200&mode=drink"
    assert client.get(q).json["currency"] == "EUR"  # no country, so Google's prices decide
    j = client.get(q + "&country=PT").json
    assert j["currency"] == "EUR" and all(r["place"]["price"]["currency"] == "EUR" for r in j["results"])


def test_old_plans_without_a_currency_still_export_in_dollars(places):
    p = planner.build_plan(places, {"lat": C[0], "lon": C[1], "name": "x"}, [FRI], 2, 60, "dive", False, False, False, {}, [])
    p.pop("currency")
    plan = planner.finalize(planner.clean_plan(p))
    assert plan["currency"] == "USD" and "$" in export.to_text(plan)
    assert "About $" in export.to_ics(plan, now=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_page_carries_the_currency_table(client):
    html = client.get("/").data.decode()
    assert '"EUR"' in html and '"PT"' in html

