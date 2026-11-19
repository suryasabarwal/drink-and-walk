"""Bars and food from Google Places API (New). Optional, and the best data the app can get.

Set GOOGLE_PLACES_KEY to turn it on. Without it, or when Google fails, the app uses OpenStreetMap.

What Google adds over the open map: a real price level (and often a typical spend range), real
opening hours, live music and outdoor seating flags, and ratings.

Cost control. Field masks here include atmosphere fields (liveMusic, servesBeer, outdoorSeating),
which puts each call in Google's "Enterprise + Atmosphere" tier. That tier has a free monthly
allowance, so:
  * the app counts calls against a daily budget (DW_GOOGLE_DAILY_LIMIT, default 30)
  * answers are kept for a short while so swaps, share links and nearby searches reuse them
  * the "live music" and "late food" searches only run when someone asks for them
Set a matching daily quota in Google Cloud too, so a bug can never run up a bill.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .. import config, geo
from ..places import FANCY, _vibe, estimate_price, merge_duplicates
from . import SourceDown
from .http import session, take_quota

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

FIELDS = ",".join(
    "places." + f
    for f in (
        "id", "displayName", "location", "types", "primaryType", "shortFormattedAddress", "businessStatus",
        "priceLevel", "priceRange", "regularOpeningHours", "rating", "userRatingCount", "websiteUri",
        "googleMapsUri", "liveMusic", "outdoorSeating", "servesBeer", "servesCocktails", "servesWine",
    )
)

# Each search returns at most 20 places, so a neighborhood takes a few of them.
NEARBY_SEARCHES = {
    "bars_popular": {"includedTypes": ["bar", "pub"], "rankPreference": "POPULARITY"},
    "bars_close": {"includedTypes": ["bar", "pub"], "rankPreference": "DISTANCE"},
    "cheap_food": {
        "includedTypes": ["fast_food_restaurant", "pizza_restaurant", "hamburger_restaurant",
                          "mexican_restaurant", "sandwich_shop", "meal_takeaway"],
        "rankPreference": "POPULARITY",
    },
    "restaurants": {"includedTypes": ["restaurant"], "rankPreference": "POPULARITY"},
    # more bars to swap between, and real cafes and quiet spots for the breather
    "pubs": {"includedTypes": ["pub"], "rankPreference": "POPULARITY"},
    "cafes": {"includedTypes": ["cafe", "coffee_shop"], "rankPreference": "POPULARITY"},
}
TEXT_SEARCHES = {"live": "live music bar", "late": "late night food"}

PRICEY_TYPES = {"wine_bar", "cocktail_bar", "lounge_bar", "fine_dining_restaurant", "steak_house"}
DRINK_TYPES = {"bar", "pub", "wine_bar", "cocktail_bar", "lounge_bar", "sports_bar", "irish_pub", "brewpub", "beer_garden", "bar_and_grill"}
FAST_TYPES = {"fast_food_restaurant", "meal_takeaway", "sandwich_shop", "hamburger_restaurant", "hot_dog_stand", "food_court"}
CAFE_TYPES = {"cafe", "coffee_shop", "bakery", "tea_house"}
LODGING_TYPES = {"hotel", "lodging", "resort_hotel", "motel", "inn", "hostel", "bed_and_breakfast", "extended_stay_hotel", "guest_house"}
TICKETED_TYPES = {"night_club", "concert_hall", "event_venue", "performing_arts_theater"}
CUISINE_FROM_TYPE = {
    "pizza_restaurant": "pizza", "hamburger_restaurant": "burger", "mexican_restaurant": "mexican",
    "sandwich_shop": "sandwich", "chinese_restaurant": "chinese", "thai_restaurant": "thai",
    "vietnamese_restaurant": "vietnamese", "indian_restaurant": "indian", "ramen_restaurant": "ramen",
    "korean_restaurant": "korean", "american_restaurant": "american", "barbecue_restaurant": "bbq",
}
LEVEL_TIER = {
    "PRICE_LEVEL_FREE": "cheap", "PRICE_LEVEL_INEXPENSIVE": "cheap", "PRICE_LEVEL_MODERATE": "ok",
    "PRICE_LEVEL_EXPENSIVE": "pricey", "PRICE_LEVEL_VERY_EXPENSIVE": "pricey",
}


def enabled() -> bool:
    return bool(config.GOOGLE_PLACES_KEY)


# ---- converting one Google place into the app's place shape ---------------------------------

def _week(opening: dict[str, Any] | None) -> list[list[list[int]]] | None:
    """Google periods -> 7 days (Mon=0) of [start, end] minutes. End may pass 1440 for late closes."""
    periods = (opening or {}).get("periods")
    if not periods:
        return None
    week: list[list[list[int]]] = [[] for _ in range(7)]
    for p in periods:
        o, c = p.get("open"), p.get("close")
        if not o or "day" not in o:
            continue
        d = (o["day"] + 6) % 7  # Google counts from Sunday
        start = o.get("hour", 0) * 60 + o.get("minute", 0)
        if not c:  # open around the clock
            return [[[0, 1440]] for _ in range(7)]
        cd = (c["day"] + 6) % 7
        end = ((cd - d) % 7) * 1440 + c.get("hour", 0) * 60 + c.get("minute", 0)
        if end <= start:
            end += 1440
        week[d].append([start, min(end, start + 2 * 1440)])
    return week


def _amenity(types: set[str], primary: str) -> str:
    if types & TICKETED_TYPES and not types & DRINK_TYPES:
        return "nightclub"
    if "pub" in types or "irish_pub" in types:
        return "pub"
    if primary in DRINK_TYPES or (types & DRINK_TYPES and not primary.endswith("restaurant")):
        return "bar"
    if primary in CAFE_TYPES:
        return "cafe"
    if primary in FAST_TYPES or (types & FAST_TYPES and "restaurant" not in primary):
        return "fast_food"
    return "restaurant"


def _price(g: dict[str, Any], amenity: str, name: str, cuisine: str, types: set[str]) -> dict[str, Any]:
    p = estimate_price(amenity, name, {"cuisine": cuisine})
    level = g.get("priceLevel")
    tier = LEVEL_TIER.get(level)
    pricey_kind = bool(types & PRICEY_TYPES) or (g.get("servesCocktails") and not g.get("servesBeer") and amenity == "bar")
    rng = g.get("priceRange") or {}
    lo, hi = (rng.get("startPrice") or {}), (rng.get("endPrice") or {})
    if lo.get("currencyCode") == "USD" and lo.get("units"):
        low = int(lo["units"])
        high = int(hi["units"]) if hi.get("units") else low + 10
        p.update(low=low, high=high, mid=round((low + high) / 2), basis=f"Google says people usually spend ${low} to ${high}")
        tier = tier or ("cheap" if p["mid"] <= 14 else "ok" if p["mid"] <= 22 else "pricey")
        # Google calls $20 to $30 bars "moderate". For a drinks stop on a cheap night, that is not.
        drinks = amenity in ("bar", "pub", "nightclub")
        if (drinks and (low >= 20 or high >= 45)) or (not drinks and (low >= 25 or high >= 60)):
            tier = "pricey"
    elif tier:
        scale = {"cheap": 0.85, "ok": 1.0, "pricey": 1.6}[tier]
        p.update(low=round(p["low"] * scale), high=round(p["high"] * scale), mid=round(p["mid"] * scale),
                 basis="From Google's price level and the type of place")
    if tier:
        p["tier"] = tier
    if pricey_kind or FANCY.search(name):
        p["tier"] = "pricey"
    p["estimate"] = True
    p["source"] = "google" if (tier or rng) else "type"
    return p


def normalize(g: dict[str, Any]) -> dict[str, Any] | None:
    if g.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
        return None
    name = ((g.get("displayName") or {}).get("text") or "").strip()
    loc = g.get("location") or {}
    if not name or "latitude" not in loc or not g.get("id"):
        return None
    types = set(g.get("types") or [])
    primary = g.get("primaryType") or ""
    if primary in LODGING_TYPES:
        return None  # a hotel turns up in bar searches, and hotel bars are not a cheap night
    amenity = _amenity(types, primary)
    cuisine = next((CUISINE_FROM_TYPE[t] for t in [primary, *types] if t in CUISINE_FROM_TYPE), "")
    live = bool(g.get("liveMusic"))
    outdoor = bool(g.get("outdoorSeating"))
    return {
        "id": "g:" + g["id"][:200],
        "name": name[:80],
        "lat": float(loc["latitude"]),
        "lon": float(loc["longitude"]),
        "amenity": amenity,
        "cuisine": cuisine,
        "address": (g.get("shortFormattedAddress") or "")[:80],
        "hours_raw": None,
        "hours_week": _week(g.get("regularOpeningHours")),
        "website": (g.get("websiteUri") or "")[:200],
        "gmaps": (g.get("googleMapsUri") or "")[:300],
        "phone": "",
        "live_music": live,
        "outdoor_seating": outdoor,
        "no_cover": False,
        "ticketed": amenity == "nightclub",
        "happy_hint": None,  # Google does not list happy hours, so nothing is claimed
        "rating": g.get("rating"),
        "rating_count": g.get("userRatingCount") or 0,
        "vibe": _vibe({"outdoor_seating": "yes" if outdoor else "no"}, name, amenity if amenity != "nightclub" else "music_venue", live),
        "price": _price(g, amenity, name, cuisine, types),
    }


# ---- fetching -------------------------------------------------------------------------------

def _cache_file(kind: str, lat: float, lon: float, radius: int):
    key = hashlib.sha1(f"{kind}|{lat:.3f}|{lon:.3f}|{radius}".encode()).hexdigest()[:16]
    return config.CACHE_DIR / f"google_{key}.json"


def _call(kind: str, lat: float, lon: float, radius: int) -> list[dict[str, Any]]:
    path = _cache_file(kind, lat, lon, radius)
    try:
        hit = json.loads(path.read_text())
        if time.time() - hit["fetched"] < config.GOOGLE_CACHE_HOURS * 3600:
            return hit["places"]
    except (OSError, ValueError, KeyError):
        pass
    if not take_quota("google", config.GOOGLE_DAILY_LIMIT):
        raise SourceDown("google: daily budget used up")
    circle = {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius)}
    if kind in NEARBY_SEARCHES:
        url, body = NEARBY_URL, {**NEARBY_SEARCHES[kind], "maxResultCount": 20, "locationRestriction": {"circle": circle}}
    else:
        url, body = TEXT_URL, {"textQuery": TEXT_SEARCHES[kind], "pageSize": 20, "locationBias": {"circle": circle}}
    try:
        r = session.post(url, json=body, timeout=config.HTTP_TIMEOUT,
                         headers={"X-Goog-Api-Key": config.GOOGLE_PLACES_KEY, "X-Goog-FieldMask": FIELDS})
    except OSError as exc:
        raise SourceDown(f"google: {type(exc).__name__}") from exc
    if r.status_code != 200:
        try:
            msg = (r.json().get("error") or {}).get("status", "")
        except ValueError:
            msg = ""
        raise SourceDown(f"google answered {r.status_code} {msg}".strip())
    places = r.json().get("places") or []
    try:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched": time.time(), "places": places}))
    except OSError:
        pass
    return places


def places_near(lat: float, lon: float, radius: int, want_live: bool = False, want_late: bool = False):
    """(places, meta) within radius of the point. Raises SourceDown if the core searches fail."""
    slat, slon = round(lat, 3), round(lon, 3)  # about 100 m, so nearby start points share answers
    kinds = list(NEARBY_SEARCHES) + (["live"] if want_live else []) + (["late"] if want_late else [])
    raw: dict[str, dict[str, Any]] = {}
    failures = []
    for kind in kinds:
        try:
            for g in _call(kind, slat, slon, radius):
                raw.setdefault(g.get("id"), g)
        except SourceDown as exc:
            failures.append(str(exc))
            if kind in NEARBY_SEARCHES and not raw:
                raise  # the first core search failed, so let the caller fall back to the open map
    out = []
    for g in raw.values():
        p = normalize(g)
        if p and geo.haversine_m(lat, lon, p["lat"], p["lon"]) <= radius:
            out.append(p)
    meta = {"source": "google", "searches": len(kinds)}
    if failures:
        meta["warning"] = failures[0]
    return merge_duplicates(out), meta
