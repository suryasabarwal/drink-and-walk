"""Starts the app with every outside source replaced by the synthetic fixtures in tests/fixtures.

Used only to look at the screens without internet. The business names in the fixtures are made up,
and this file is never imported by the real app.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures"

from dw import config, money  # noqa: E402

tmp = Path(tempfile.mkdtemp())
config.DATA_DIR = tmp
config.CACHE_DIR = tmp / "cache"

from dw.sources import geocode, overpass, ticketmaster, weather  # noqa: E402
import app as appmod  # noqa: E402

els = json.loads((FIX / "overpass_sample.json").read_text())["elements"]
anchors = json.loads((FIX / "overpass_anchors.json").read_text())["elements"]
overpass.fetch_elements = lambda lat, lon, r: (els, {"source": "fixture"})
overpass._run = lambda path, q: (anchors, {"source": "fixture"})
geocode.search_cities = lambda q, count=6: [{"label": "Testville, New York, US", "name": "Testville", "lat": 42.8864, "lon": -78.8784, "country": "US", "timezone": "", "population": 1, "currency": money.USD.as_dict(), "budget": money.budget_choices(money.USD)}]
geocode.locate = lambda q, lat, lon: [{"label": "Fixture Inn, 1 Test Street, Testville", "lat": 42.8870, "lon": -78.8790}]
weather.forecast = lambda lat, lon, a, b: {a.isoformat(): {"hi_c": 3, "lo_c": -2, "rain_pct": 60}}
ticketmaster.events = lambda *a, **k: []
appmod._hits.clear()
appmod.limited  # rate limits stay on, as in production

if __name__ == "__main__":
    appmod.app.run(port=5055)
