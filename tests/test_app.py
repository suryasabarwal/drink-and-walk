import json
from datetime import date, timedelta

import pytest
import requests

FRI = (date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7))
BODY = {"city": {"name": "Testville", "country": "US"}, "start": FRI.isoformat(), "end": (FRI + timedelta(days=1)).isoformat(),
        "people": 4, "budget_pp": 60, "stay": {"lat": 42.8864, "lon": -78.8784, "name": "Test Hotel"}, "vibe": "dive",
        "live_music": True, "late_night": True, "free_only": False}


def test_pages_and_health(client):
    assert client.get("/").status_code == 200 and b"Drink and Walk" in client.get("/").data
    assert client.get("/healthz").data == b"ok"


def test_city_and_anchors(client):
    assert client.get("/api/cities?q=te").json["results"][0]["name"] == "Testville"
    r = client.get("/api/anchors?lat=42.88&lon=-78.87").json["results"]
    assert {a["kind"] for a in r} == {"Neighborhood", "Train station"}


def test_plan_end_to_end(client):
    j = client.post("/api/plan", json=BODY).json
    assert len(j["nights"]) == 2 and j["nights"][0]["stops"]
    assert "DRINK AND WALK" in j["text"] and j["safety"] and any(b["level"] for b in j["banners"])
    assert len(j["safety"]) == 4  # US gets the 21+ line


def test_plan_rejects_bad_input(client):
    for patch in ({"start": "nope"}, {"end": (FRI - timedelta(days=2)).isoformat()}, {"end": (FRI + timedelta(days=9)).isoformat()},
                  {"people": 0}, {"budget_pp": 2}, {"start": "2020-01-01", "end": "2020-01-02"}, {"stay": {"lat": 999, "lon": 0}}):
        r = client.post("/api/plan", json={**BODY, **patch})
        assert r.status_code == 400 and r.json["error"], patch


def test_recompute_and_ics(client):
    plan = client.post("/api/plan", json=BODY).json
    for n in plan["nights"]:
        for s in n["stops"]:
            s.pop("alternatives", None)
    r = client.post("/api/recompute", json={"plan": plan}).json
    assert r["nights"][0]["totals"]["per_person"] == plan["nights"][0]["totals"]["per_person"]
    ics = client.post("/api/ics", json={"plan": plan})
    assert ics.mimetype == "text/calendar" and b"BEGIN:VEVENT" in ics.data
    assert client.post("/api/ics", json={"plan": {}}).status_code == 400


def test_recompute_ignores_junk_fields(client):
    junk = {"stay": {"lat": "x"}, "people": "many", "nights": [{"date": "2026-12-04", "stops": [{"slot": "<script>", "place": {"name": "<b>x</b>", "website": "javascript:alert(1)", "id": "bad"}}]}]}
    r = client.post("/api/recompute", json={"plan": junk})
    assert r.status_code == 200


def test_nearby(client):
    r = client.get("/api/nearby?lat=42.8864&lon=-78.8784&day=4&minute=1200&mode=drink").json
    assert r["results"] and all(x["walk"]["min"] >= 0 for x in r["results"])
    assert client.get("/api/nearby?lat=42.8864&lon=-78.8784&day=4&minute=1200&mode=bogus").status_code == 400
    assert client.get("/api/nearby?lat=abc&lon=1&day=1&minute=1").status_code == 400


def test_deal_board_roundtrip_and_spam_blocked(client):
    ok = client.post("/api/deals", json={"place_id": "n1001", "place_name": "Rusty Anchor Tavern", "text": "$3 pints Tuesday", "when": "Tue"})
    assert ok.status_code == 201
    assert client.post("/api/deals", json={"place_id": "n1001", "place_name": "x", "text": "see www.x.com"}).status_code == 400
    plan = client.post("/api/plan", json=BODY).json
    texts = [d["text"] for n in plan["nights"] for s in n["stops"] for d in s["deals"]]
    assert texts == [] or "$3 pints Tuesday" in texts


def test_rate_limit(client):
    codes = [client.get("/api/cities?q=te").status_code for _ in range(62)]
    assert 429 in codes


# ---- sources being down ----
def test_map_source_down_gives_friendly_503(monkeypatch, client):
    from dw.sources import overpass, SourceDown

    def boom(*a, **k):
        raise SourceDown("both servers failed")
    monkeypatch.setattr(overpass, "fetch_elements", boom)
    r = client.post("/api/plan", json=BODY)
    assert r.status_code == 503 and "busy" in r.json["error"]


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d = status, data or {}
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError("bad", response=self)


def test_overpass_falls_back_to_backup_server_then_cache(monkeypatch, elements):
    from dw.sources import overpass
    calls = []
    def post(url, data=None, timeout=None):
        calls.append(url)
        return FakeResp(504) if "overpass-api.de" in url else FakeResp(200, {"elements": elements})
    monkeypatch.setattr(overpass.session, "post", post)
    monkeypatch.setattr(overpass, "throttle", lambda *a: None)
    els, meta = overpass.fetch_elements(42.88, -78.87, 1500)
    assert len(calls) == 2 and "private.coffee" in calls[1] and meta["source"] == "live"
    # second call is served from cache with no network
    calls.clear()
    els2, meta2 = overpass.fetch_elements(42.8801, -78.8701, 1500)
    assert not calls and meta2["source"] == "cache"


def test_overpass_all_down_uses_stale_cache_else_raises(monkeypatch, elements):
    from dw import config
    from dw.sources import overpass, SourceDown
    import time
    monkeypatch.setattr(overpass, "throttle", lambda *a: None)
    def down(*a, **k): raise requests.ConnectionError("no")
    monkeypatch.setattr(overpass.session, "post", down)
    with pytest.raises(SourceDown):
        overpass.fetch_elements(10.0, 10.0, 1500)
    path = overpass._cache_path(overpass._snap(10.0), overpass._snap(10.0), 2100)
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched": time.time() - 30 * 86400, "elements": elements}))
    els, meta = overpass.fetch_elements(10.0, 10.0, 1500)
    assert meta["source"] == "stale-cache" and els


def test_daily_budget_stops_hammering_the_public_server(monkeypatch):
    from dw import config
    from dw.sources import overpass, SourceDown
    monkeypatch.setattr(config, "OVERPASS_DAILY_LIMIT", 0)
    called = []
    monkeypatch.setattr(overpass.session, "post", lambda *a, **k: called.append(1))
    with pytest.raises(SourceDown):
        overpass.fetch_elements(11.0, 11.0, 1500)
    assert not called


def test_weather_failure_is_reported_not_hidden(monkeypatch):
    from dw import notes
    from dw.sources import weather
    def down(*a, **k): raise requests.ConnectionError("no")
    monkeypatch.setattr(weather.session, "get", down)
    assert weather.forecast(1, 1, date.today(), date.today()) is None
    assert any("weather forecast" in b["text"] for b in notes.banners([date.today()], "US", None))
    # past the forecast range there is nothing to know yet, which is not a failure
    assert weather.forecast(1, 1, date.today() + timedelta(days=40), date.today() + timedelta(days=41)) == {}


def test_weather_parses_and_caches(monkeypatch):
    from dw.sources import weather
    t = date.today()
    days = [(t + timedelta(days=i)).isoformat() for i in range(16)]
    body = {"daily": {"time": days, "temperature_2m_max": [30] * 16, "temperature_2m_min": [-2] * 16, "precipitation_probability_max": [None] + [70] * 15}}
    calls = []
    def get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResp(200, body)
    monkeypatch.setattr(weather.session, "get", get)
    wx = weather.forecast(30.27, -97.74, t, t + timedelta(days=1))
    assert set(wx) == set(days[:2]) and wx[days[0]]["rain_pct"] is None and wx[days[1]]["lo_c"] == -2
    weather.forecast(30.2701, -97.7399, t + timedelta(days=2), t + timedelta(days=3))
    assert len(calls) == 1  # second plan nearby reuses the cached forecast


def test_ticketmaster_off_without_key_and_failure_safe(monkeypatch):
    from dw import config
    from dw.sources import ticketmaster
    assert ticketmaster.events(1, 1, date.today(), date.today()) == []
    monkeypatch.setattr(config, "TICKETMASTER_KEY", "k")
    def down(*a, **k): raise requests.ConnectionError("no")
    monkeypatch.setattr(ticketmaster.session, "get", down)
    monkeypatch.setattr(ticketmaster, "throttle", lambda *a: None)
    assert ticketmaster.events(1, 1, date.today(), date.today()) == []


def test_overpass_partial_answer_is_not_cached_and_backup_is_tried(monkeypatch, elements):
    from dw.sources import overpass
    calls = []
    def post(url, data=None, timeout=None):
        calls.append(url)
        if "overpass-api.de" in url:
            return FakeResp(200, {"elements": [], "remark": "runtime error: Query timed out in \"query\" at line 3"})
        return FakeResp(200, {"elements": elements})
    monkeypatch.setattr(overpass.session, "post", post)
    monkeypatch.setattr(overpass, "throttle", lambda *a: None)
    els, meta = overpass.fetch_elements(20.0, 20.0, 1500)
    assert len(calls) == 2 and els and meta["server"] == "overpass.private.coffee"


def test_failed_server_rests_instead_of_making_every_visitor_wait(monkeypatch, elements):
    from dw.sources import overpass, SourceDown
    monkeypatch.setattr(overpass, "throttle", lambda *a: None)
    calls = []
    def down(url, **k):
        calls.append(url)
        raise requests.ConnectTimeout("slow")
    monkeypatch.setattr(overpass.session, "post", down)
    with pytest.raises(SourceDown):
        overpass.fetch_elements(30.0, 30.0, 1500)
    assert len(calls) == 2
    with pytest.raises(SourceDown):
        overpass.fetch_elements(31.0, 31.0, 1500)
    assert len(calls) == 2  # both servers resting, no new waits, no quota spent


def test_city_search_down_names_the_right_source(monkeypatch, client):
    from dw.sources import geocode, SourceDown
    def boom(*a, **k):
        raise SourceDown("city search: ConnectionError")
    monkeypatch.setattr(geocode, "search_cities", boom)
    r = client.get("/api/cities?q=austin")
    assert r.status_code == 503 and r.json["error"].startswith("City search is busy")


def test_http_session_retries_dropped_gets_but_not_rate_limits():
    from dw.sources.http import session
    retry = session.get_adapter("https://example.org").max_retries
    assert retry.total >= 1 and 429 not in retry.status_forcelist and "POST" not in retry.allowed_methods


def test_rate_limited_source_with_retry_after_does_not_stall():
    """Open-Meteo answers 429 with Retry-After when its daily limit is hit. That must fail fast."""
    import time
    from urllib3.response import HTTPResponse
    from dw.sources.http import session
    retry = session.get_adapter("https://example.org").max_retries
    resp = HTTPResponse(status=429, headers={"Retry-After": "36000"})
    assert not retry.is_retry("GET", 429, has_retry_after=True)
    t = time.monotonic()
    retry.sleep(resp)
    assert time.monotonic() - t < 1


def test_weather_falls_back_to_met_norway_when_open_meteo_says_no(monkeypatch):
    """Synthetic MET Norway shape: hourly points in UTC with instant temperature and next hour rain."""
    from datetime import datetime, timezone
    from dw import notes
    from dw.sources import weather
    t = date.today()
    start = datetime(t.year, t.month, t.day, 5, tzinfo=timezone.utc)  # lon 0, so UTC is local
    series = []
    for h in range(48):
        when = start + timedelta(hours=h)
        series.append({"time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "data": {"instant": {"details": {"air_temperature": -3 + h % 24 * 0.5}},
                                "next_1_hours": {"details": {"precipitation_amount": 0.6 if 18 <= when.hour <= 21 else 0.0}}}})
    def get(url, params=None, timeout=None):
        if "open-meteo" in url:
            return FakeResp(429, {"reason": "Daily API request limit exceeded"})
        return FakeResp(200, {"properties": {"timeseries": series}})
    monkeypatch.setattr(weather.session, "get", get)
    wx = weather.forecast(51.5, 0.0, t, t)
    day = wx[t.isoformat()]
    assert day["rain_pct"] is None and day["rain_mm"] == 2.4 and day["lo_c"] < 0
    texts = [b["text"] for b in notes.banners([t], "GB", wx)]
    assert any("Rain expected" in x and "2.4 mm" in x for x in texts) and any("below freezing" in x for x in texts)


def test_weather_says_why_when_every_source_fails(monkeypatch):
    from dw.sources import weather
    monkeypatch.setattr(weather.session, "get", lambda *a, **k: FakeResp(429, {}))
    assert weather.forecast(1, 1, date.today(), date.today()) is None
    assert "open-meteo: 429" in weather.last_error and "met.no: 429" in weather.last_error
