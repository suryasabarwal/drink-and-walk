"""Local currency. Place data here is synthetic."""
from datetime import date, timedelta

import pytest

from dw import money
from dw.sources import google_places as G

EUR_PT = money.for_country("PT")


def test_formats_read_like_local_prices():
    assert money.fmt(14, money.USD) == "$14"
    assert money.fmt(14, EUR_PT) == "€8"                       # cheaper night out, not just other money
    assert money.fmt(14, money.for_country("JP")) == "¥1,400"
    assert money.fmt(14, money.for_country("DK")) == "91 kr"   # suffix currencies read the local way
    assert money.fmt(14, money.for_country("GB")) == "£10"
    assert money.for_country("XX") is None


def test_budget_choices_are_round_local_numbers():
    jp = money.budget_choices(money.for_country("JP"))
    assert jp["default"] == 5000 and jp["min"] == 2000 and jp["step"] == 500
    pt = money.budget_choices(EUR_PT)
    assert pt["default"] == 28 and pt["chips"] == [16, 28, 41, 55]


def test_from_dict_only_accepts_known_currencies():
    assert money.from_dict({"code": "EUR", "level": 0.55}) == EUR_PT
    assert money.from_dict({"code": "XYZ", "level": 999}) == money.USD
    assert money.from_dict({"code": "EUR", "level": 123}).code == "EUR"  # known code, but never a made-up level


def g(i, name, primary, types, rng=None, level="PRICE_LEVEL_INEXPENSIVE", cur="EUR"):
    d = {"id": f"ChIJmoney{i:03d}", "displayName": {"text": name}, "primaryType": primary, "types": types, "priceLevel": level,
         "location": {"latitude": 38.71, "longitude": -9.14}, "businessStatus": "OPERATIONAL", "userRatingCount": 50}
    if rng:
        d["priceRange"] = {"startPrice": {"currencyCode": cur, "units": str(rng[0])}, "endPrice": {"currencyCode": cur, "units": str(rng[1])}}
    return d


def test_google_range_in_euros_is_used_and_labeled_in_euros():
    p = G.normalize(g(1, "Tasca Teste", "pub", ["pub", "bar"], (5, 10)), EUR_PT)
    assert p["price"]["basis"] == "Google says people usually spend €5 to €10"
    assert money.fmt(p["price"]["mid"], EUR_PT) == "€8"  # the shown price matches Google's range
    pricey = G.normalize(g(2, "Bar Caro Teste", "bar", ["bar"], (20, 40)), EUR_PT)
    assert pricey["price"]["tier"] == "pricey"  # €20 to €40 is a lot for Lisbon


def test_currency_is_read_from_google_when_the_country_is_unknown():
    raw = {x["id"]: x for x in [g(1, "A", "bar", ["bar"], (5, 10)), g(2, "B", "bar", ["bar"], (6, 12)), g(3, "C", "bar", ["bar"], (5, 9), cur="USD")]}
    assert G._currency_from(raw).code == "EUR"


def test_lisbon_plan_is_in_euros_everywhere(client):
    fri = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    body = {"city": {"name": "Lisbon", "country": "PT"}, "start": fri.isoformat(), "end": fri.isoformat(), "people": 2, "budget_pp": 30,
            "stay": {"lat": 42.8864, "lon": -78.8784, "name": "Bairro Alto"}, "vibe": "dive"}
    plan = client.post("/api/plan", json=body).json
    assert plan["currency"]["code"] == "EUR" and "€" in plan["text"] and "$" not in plan["text"]
    assert round(plan["budget_pp"] * plan["currency"]["level"]) == 30  # the €30 typed in comes back as €30
    assert all("$" not in t for n in plan["nights"] for t in n["tips"] + [n["totals"]["message"]])
    for n in plan["nights"]:
        for s in n["stops"]:
            s.pop("alternatives", None)
    again = client.post("/api/recompute", json={"plan": plan}).json
    assert "€" in again["text"] and "$" not in again["text"]
    ics = client.post("/api/ics", json={"plan": plan}).data.decode()
    assert "€" in ics and "About $" not in ics


def test_lisbon_budget_out_of_range_in_euros_is_rejected(client):
    fri = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    body = {"city": {"name": "Lisbon", "country": "PT"}, "start": fri.isoformat(), "end": fri.isoformat(), "people": 2, "budget_pp": 1,
            "stay": {"lat": 42.8864, "lon": -78.8784, "name": "x"}, "vibe": "dive"}
    assert client.post("/api/plan", json=body).status_code == 400


def test_nearby_and_city_search_carry_the_currency(client):
    r = client.get("/api/nearby?lat=42.8864&lon=-78.8784&day=4&minute=1200&mode=drink&country=GB").json
    assert r["meta"]["currency"]["code"] == "GBP"
    c = client.get("/api/cities?q=te").json["results"][0]
    assert c["currency"]["code"] == "USD" and c["budget"]["default"] == 50
