"""Finding a spot inside a city. Responses are synthetic, shaped like the documented APIs."""
import pytest

from dw import config
from dw.sources import SourceDown, geocode, google_places as G


class Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise OSError("bad")


SUGGEST = {"suggestions": [
    {"placePrediction": {"placeId": "ChIJdlfphase1", "text": {"text": "DLF Phase 1, Sector 26, Gurugram, Haryana, India"},
                         "structuredFormat": {"mainText": {"text": "DLF Phase 1"}, "secondaryText": {"text": "Sector 26, Gurugram, Haryana, India"}}}},
    {"queryPrediction": {"text": {"text": "dlf phase 1 bars"}}},
]}
DETAILS = {"id": "ChIJdlfphase1", "displayName": {"text": "DLF Phase 1"}, "location": {"latitude": 28.4717, "longitude": 77.0957},
           "addressComponents": [{"longText": "Gurugram", "shortText": "Gurugram", "types": ["locality", "political"]},
                                 {"longText": "India", "shortText": "IN", "types": ["country", "political"]}]}


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "k")
    sent = {}
    def post(url, json=None, timeout=None, headers=None):
        sent["body"] = json
        return Resp(200, SUGGEST)
    def get(url, params=None, timeout=None, headers=None):
        sent["details"] = (url, params, headers["X-Goog-FieldMask"])
        return Resp(200, DETAILS)
    monkeypatch.setattr(G.session, "post", post)
    monkeypatch.setattr(G.session, "get", get)
    return sent


def test_neighborhood_suggestions_and_pick(google):
    got = G.autocomplete("DLF Phase 1", "tok123", near=(28.46, 77.03))
    assert got == [{"id": "ChIJdlfphase1", "label": "DLF Phase 1", "sub": "Sector 26, Gurugram, Haryana, India"}]
    assert google["body"]["sessionToken"] == "tok123" and google["body"]["locationBias"]["circle"]["radius"] == 30000.0
    pt = G.place_point("ChIJdlfphase1", "tok123")
    assert pt == {"lat": 28.4717, "lon": 77.0957, "name": "DLF Phase 1", "country": "IN", "town": "Gurugram"}
    assert google["details"][1] == {"sessionToken": "tok123"} and "location" in google["details"][2]


def test_endpoints_return_suggestions_then_a_point_with_local_currency(google, client):
    r = client.get("/api/places?q=DLF%20Phase%201&session=tok").json
    assert r["live"] and r["results"][0]["label"] == "DLF Phase 1"
    pt = client.get("/api/place?id=ChIJdlfphase1&session=tok").json
    assert pt["country"] == "IN" and pt["currency"]["code"] == "INR" and pt["town"] == "Gurugram"
    assert client.get("/api/place?id=../../etc").status_code == 400


def test_search_budget_and_failure_fall_back_to_open_map(monkeypatch, google, client):
    monkeypatch.setattr(config, "GOOGLE_AC_DAILY_LIMIT", 0)
    monkeypatch.setattr(geocode, "find_place", lambda q: [{"label": "Vasant Vihar", "sub": "New Delhi, Delhi, India", "lat": 28.56, "lon": 77.16, "country": "IN", "town": "New Delhi"}])
    r = client.get("/api/places?q=Vasant%20Vihar").json
    assert r["live"] is False and r["results"][0]["country"] == "IN"


def test_open_map_search_reads_country_and_town(monkeypatch):
    rows = [{"lat": "28.5602", "lon": "77.1600", "name": "Vasant Vihar", "display_name": "Vasant Vihar, Vasant Vihar Tehsil, New Delhi, Delhi, India",
             "address": {"suburb": "Vasant Vihar", "city": "New Delhi", "country_code": "in"}}]
    monkeypatch.setattr(geocode, "throttle", lambda *a: None)
    monkeypatch.setattr(geocode.session, "get", lambda *a, **k: Resp(200, rows))
    got = geocode.find_place("Vasant Vihar New Delhi")
    assert got[0]["label"] == "Vasant Vihar" and got[0]["country"] == "IN" and got[0]["town"] == "New Delhi"
    assert got[0]["sub"] == "Vasant Vihar Tehsil, New Delhi, Delhi"


def test_google_down_raises_cleanly(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "k")
    monkeypatch.setattr(G.session, "post", lambda *a, **k: Resp(403, {}))
    with pytest.raises(SourceDown):
        G.autocomplete("Sector 26")
