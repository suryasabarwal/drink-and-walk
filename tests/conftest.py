import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures"
CENTER = (42.8864, -78.8784)  # synthetic test data placed around a point; not real businesses


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch):
    from dw import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "TICKETMASTER_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_PLACES_KEY", "")
    from dw.sources import overpass, weather
    overpass._resting.clear()
    weather._cache.clear()


@pytest.fixture
def elements():
    return json.loads((FIX / "overpass_sample.json").read_text())["elements"]


@pytest.fixture
def places(elements):
    from dw.places import from_elements
    return from_elements(elements)


@pytest.fixture
def client(monkeypatch, elements):
    """Flask client with every outside source replaced by fixtures. Nothing touches the network."""
    import app as appmod
    from dw.sources import overpass, geocode, weather, ticketmaster

    monkeypatch.setattr(overpass, "fetch_elements", lambda lat, lon, r: (elements, {"source": "fixture"}))
    anchors = json.loads((FIX / "overpass_anchors.json").read_text())["elements"]
    monkeypatch.setattr(overpass, "_run", lambda path, q: (anchors, {"source": "fixture"}))
    monkeypatch.setattr(weather, "forecast", lambda *a, **k: {})
    monkeypatch.setattr(ticketmaster, "events", lambda *a, **k: [])
    monkeypatch.setattr(geocode, "search_cities", lambda q, count=6: [{"label": "Testville, NY, US", "name": "Testville", "lat": CENTER[0], "lon": CENTER[1], "country": "US", "timezone": "", "population": 1}])
    appmod._hits.clear()
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()
