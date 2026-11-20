import time
from datetime import date, datetime, timezone

import pytest

from dw import deals, export, notes, planner
from dw.planner import finalize

STAY = {"lat": 42.8864, "lon": -78.8784, "name": "Test Hotel"}


def test_thanksgiving_eve_and_nye_warn():
    t = notes.banners([date(2026, 11, 25)], "US", {})
    assert any("Thanksgiving" in b["text"] and b["level"] == "warn" for b in t)
    assert any("New Year" in b["text"] for b in notes.banners([date(2026, 12, 31)], "US", {}))


def test_long_weekend_flagged_and_other_countries_get_no_us_holidays():
    assert any("Memorial Day" in b["text"] for b in notes.banners([date(2026, 5, 23)], "US", {}))
    assert not any("Thanksgiving" in b["text"] for b in notes.banners([date(2026, 11, 25)], "PT", {}))


def test_weather_banners():
    b = notes.banners([date(2026, 12, 2)], "US", {"2026-12-02": {"rain_pct": 70, "lo_c": 1, "hi_c": 8}})
    assert any("Rain" in x["text"] for x in b)


def test_text_export_has_everything(places):
    p = planner.build_plan(places, STAY, [date(2026, 12, 4)], 4, 60, "dive", True, False, False, {}, [])
    p["city"] = "Testville"
    txt = export.to_text(p)
    assert "DRINK AND WALK: Testville" in txt and "google.com/maps" in txt and "estimates" in txt
    assert all(s["place"]["name"] in txt for s in p["nights"][0]["stops"])


def test_ics_is_valid_shape_and_escapes(places):
    p = planner.build_plan(places, STAY, [date(2026, 12, 4)], 4, 60, "dive", False, False, False, {}, [])
    p["nights"][0]["stops"][0]["place"]["name"] = "Bob's; Bar, Grill\nX"
    ics = export.to_ics(p, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR") and ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == len(p["nights"][0]["stops"]) == ics.count("END:VEVENT")
    assert "Bob's\\; Bar\\, Grill\\nX" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_deal_validation_and_expiry():
    d = deals.add("n1001", "Rusty Anchor", "$3 pints all night", "Tue")
    assert deals.for_places({"n1001"})["n1001"][0]["text"] == "$3 pints all night"
    for bad in ("hi", "x" * 200, "visit www.spam.com now", "mail me@x.org please"):
        with pytest.raises(deals.DealError):
            deals.add("n1001", "Rusty Anchor", bad, "")
    with pytest.raises(deals.DealError):
        deals.add("not-an-id", "x", "$3 pints all night", "")
    deals.report_gone(d["id"])
    assert "n1001" in deals.for_places({"n1001"})
    deals.report_gone(d["id"])
    assert deals.for_places({"n1001"}) == {}


def test_old_deals_expire(monkeypatch):
    deals.add("n1002", "A Bar", "$2 tacos on Monday", "")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 200 * 86400)
    assert deals.for_places({"n1002"}) == {}


def test_deal_text_allows_at_sign_but_not_links():
    import pytest
    from dw import deals
    assert deals.clean("$5 wings @ the bar", 1, 140, "deal")
    assert deals.clean("$3.50 pints all night", 1, 140, "deal")
    for bad in ("see bit.ly/x", "mail me at a@b.co", "https://x", "www.cheap", "promo at cheapbeer.com"):
        with pytest.raises(deals.DealError):
            deals.clean(bad, 1, 140, "deal")


def test_text_credits_the_source_the_places_came_from():
    from dw import export
    plan = {"people": 2, "stay": {"name": ""}, "nights": [], "google": True}
    assert "from Google Maps" in export.to_text(plan) and "OpenStreetMap" not in export.to_text(plan)
    plan["google"] = False
    assert "OpenStreetMap contributors" in export.to_text(plan)
