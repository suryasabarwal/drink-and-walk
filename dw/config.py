"""Settings. Everything is free to run; the only optional key is Ticketmaster."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DW_DATA_DIR", ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"

CONTACT = os.environ.get("DW_CONTACT", "https://github.com/suryasabarwal/drink-and-walk")
USER_AGENT = f"DrinkAndWalk/1.0 (+{CONTACT})"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# The public Overpass servers ask for light use. This counts queries across all visitors.
OVERPASS_DAILY_LIMIT = int(os.environ.get("DW_OVERPASS_DAILY_LIMIT", "80"))
PLACES_CACHE_DAYS = 7

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
TICKETMASTER_KEY = os.environ.get("TICKETMASTER_KEY", "")

# Optional: Google Places (New). Real price levels, hours, live music flags and ratings.
GOOGLE_PLACES_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
# Calls a day across all visitors. A new area costs 6 to 8 calls, then nothing for 12 hours.
GOOGLE_DAILY_LIMIT = int(os.environ.get("DW_GOOGLE_DAILY_LIMIT", "30"))
GOOGLE_CACHE_HOURS = 12
# Place search suggestions and picks a day (free monthly allowance is far larger).
GOOGLE_AC_DAILY_LIMIT = int(os.environ.get("DW_GOOGLE_AC_DAILY_LIMIT", "300"))

DEFAULT_RADIUS_M = 1500
MAX_RADIUS_M = 4000
MAX_NIGHTS = 4
MAX_PEOPLE = 20
WALK_M_PER_MIN = 80       # about 4.8 km/h
DETOUR_FACTOR = 1.25      # streets are not straight lines
HTTP_TIMEOUT = 25
# Overpass queries ask the server for up to 25 s of work; leave room for the answer to arrive.
OVERPASS_HTTP_TIMEOUT = 35
