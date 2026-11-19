"""Turn raw OpenStreetMap elements into places we can plan with.

OpenStreetMap does not carry prices or happy hours for most venues. So prices here are
estimates from the kind of place, and every one is labeled as an estimate in the app.
"""
from __future__ import annotations

import re
from typing import Any

from . import geo
from .hours import Hours, parse as parse_hours

DRINK_AMENITIES = {"bar", "pub", "biergarten"}
FOOD_AMENITIES = {"restaurant", "fast_food", "food_court", "cafe"}
TICKETED = {"music_venue", "nightclub", "events_venue", "theatre"}

FANCY = re.compile(
    r"cocktail|lounge|speakeasy|rooftop|roof top|wine|champagne|mixology|supper|bistro|"
    r"brasserie|omakase|steakhouse|sky ?bar|skybar|hotel|club ?house|oyster|tasting|apothecary|"
    r"prohibition|distill|whisk(e)?y room|cellar",
    re.I,
)
DIVEY = re.compile(r"dive|tavern|saloon|tap\b|taproom|pub\b|ale ?house|inn\b|shots?|sports|billiard|pool hall|bowl|corner|local|legion|vfw|pit", re.I)
LIVELY = re.compile(r"social|hall|garden|arcade|karaoke|stage|brew|beer hall|bier|dance|jukebox|barcade|game|rooftop|patio|music|live", re.I)
CHILL = re.compile(r"cafe|café|coffee|tea|books|library|garden|patio|wine|lounge|quiet|porch|deli|bakery", re.I)
CHEAP_CUISINE = {
    "pizza", "burger", "sandwich", "mexican", "taco", "tacos", "noodle", "noodles", "chinese", "vietnamese",
    "indian", "thai", "kebab", "diner", "ramen", "korean", "regional", "american", "hot_dog", "chicken",
    "fish_and_chips", "falafel", "bagel", "donut", "sub", "wings", "bbq", "deli", "dumpling", "pho", "burrito",
}
FOOD_VERBS = re.compile(r"pizza|slice|taco|burrito|burger|wings|deli|noodle|ramen|pho|dumpling|kebab|falafel|diner", re.I)


def _norm_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", "", name.lower())
    n = re.sub(r"^(the|a) ", "", n).strip()
    return re.sub(r"\s+", " ", n)


def _addr(tags: dict[str, str]) -> str:
    parts = [tags.get("addr:housenumber", ""), tags.get("addr:street", "")]
    street = " ".join(p for p in parts if p).strip()
    return street


def _live_music(tags: dict[str, str]) -> bool:
    if tags.get("live_music") in ("yes", "true"):
        return True
    for k, v in tags.items():
        if k.startswith("live_music:") and v not in ("no", "false"):
            return True
    return tags.get("amenity") == "music_venue"


def _happy_hint(tags: dict[str, str]) -> str | None:
    """Only report what the map actually says. Any tag with 'happy' in its key."""
    for k, v in tags.items():
        if "happy" in k.lower() and v and v.lower() not in ("no", "false"):
            return v[:120]
    return None


def _vibe(tags: dict[str, str], name: str, amenity: str, live: bool) -> dict[str, float]:
    dive = lively = chill = 0.0
    if amenity == "pub":
        dive += 0.5
    if DIVEY.search(name):
        dive += 0.5
    if amenity in ("bar",) and not FANCY.search(name):
        dive += 0.2
    if live or amenity in ("music_venue", "biergarten"):
        lively += 0.6
    if LIVELY.search(name):
        lively += 0.3
    if tags.get("outdoor_seating") == "yes":
        lively += 0.1
        chill += 0.2
    if amenity == "cafe":
        chill += 0.8
    if CHILL.search(name):
        chill += 0.4
    if amenity == "pub":
        chill += 0.25
    return {"dive": min(dive, 1.0), "lively": min(lively, 1.0), "chill": min(chill, 1.0)}


def estimate_price(amenity: str, name: str, tags: dict[str, str]) -> dict[str, Any]:
    """Per-person estimate for one typical stop. Drinks stops assume two drinks."""
    cuisine = {c.strip() for c in tags.get("cuisine", "").lower().split(";") if c.strip()}
    fancy = bool(FANCY.search(name)) or "cocktails" in cuisine or "wine" in cuisine
    if amenity in DRINK_AMENITIES or amenity == "music_venue":
        if fancy:
            low, high, basis = 24, 34, "Looks like a cocktail or wine place, so drinks run high"
        elif amenity == "pub":
            low, high, basis = 9, 14, "Typical pub prices, two drinks"
        elif amenity == "biergarten":
            low, high, basis = 10, 15, "Typical beer garden prices, two drinks"
        elif amenity == "music_venue":
            low, high, basis = 14, 28, "Two drinks plus a cover that is not listed"
        else:
            low, high, basis = 11, 18, "Typical bar prices, two drinks"
    elif amenity == "fast_food":
        low, high, basis = 7, 11, "Fast food or counter service"
    elif amenity == "cafe":
        low, high, basis = 5, 9, "Coffee and a snack"
    elif amenity in ("restaurant", "food_court"):
        if (cuisine & CHEAP_CUISINE) or FOOD_VERBS.search(name) or amenity == "food_court":
            low, high, basis = 11, 17, "Casual spot, one main dish"
        else:
            low, high, basis = 19, 32, "Sit-down restaurant, one main dish"
    else:
        low, high, basis = 12, 20, "Rough guess"
    mid = (low + high) / 2
    if amenity in ("fast_food", "cafe"):
        tier = "cheap"
    elif amenity in DRINK_AMENITIES or amenity == "music_venue":
        tier = "pricey" if fancy else ("cheap" if mid <= 13 else "ok")
    else:
        tier = "cheap" if mid <= 14 else ("ok" if mid <= 20 else "pricey")
    return {"low": low, "high": high, "mid": round(mid), "tier": tier, "basis": basis, "estimate": True}


def normalize(element: dict[str, Any]) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    amenity = tags.get("amenity", "")
    if not name or amenity not in (DRINK_AMENITIES | FOOD_AMENITIES | TICKETED):
        return None
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        c = element.get("center") or {}
        lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None
    live = _live_music(tags)
    price = estimate_price(amenity, name, tags)
    hours_raw = tags.get("opening_hours")
    return {
        "id": f"{element.get('type', 'n')[0]}{element.get('id')}",
        "name": name[:80],
        "lat": float(lat),
        "lon": float(lon),
        "amenity": amenity,
        "cuisine": tags.get("cuisine", "")[:60],
        "address": _addr(tags)[:80],
        "hours_raw": hours_raw[:200] if hours_raw else None,
        "website": (tags.get("website") or tags.get("contact:website") or "")[:200],
        "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40],
        "live_music": live,
        "outdoor_seating": tags.get("outdoor_seating") == "yes",
        "no_cover": tags.get("fee") == "no",
        "ticketed": amenity in TICKETED,
        "happy_hint": _happy_hint(tags),
        "vibe": _vibe(tags, name, amenity, live),
        "price": price,
    }


def merge_duplicates(places: list[dict[str, Any]], within_m: float = 80) -> list[dict[str, Any]]:
    """The same bar can show up as a point and as a building. Keep the one with more detail."""
    def richness(p: dict[str, Any]) -> int:
        return sum(bool(p.get(k)) for k in ("hours_raw", "website", "phone", "address", "happy_hint"))

    kept: list[dict[str, Any]] = []
    for p in sorted(places, key=richness, reverse=True):
        key = _norm_name(p["name"])
        dup = False
        for q in kept:
            if _norm_name(q["name"]) == key and geo.haversine_m(p["lat"], p["lon"], q["lat"], q["lon"]) <= within_m:
                dup = True
                q["live_music"] = q["live_music"] or p["live_music"]
                break
        if not dup:
            kept.append(p)
    return kept


def from_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for el in elements:
        p = normalize(el)
        if p:
            out.append(p)
    return merge_duplicates(out)


def open_state(place: dict[str, Any], day: int, minute: int, span: int = 60) -> bool | None:
    """True if open at the start and still open `span` minutes later. None if hours unknown."""
    week = place.get("hours_week")
    h = Hours([[tuple(r) for r in day] for day in week]) if week else parse_hours(place.get("hours_raw"))
    if not h.known:
        return None
    a = h.is_open(day, minute)
    b = h.is_open(day, minute + span)
    return bool(a and b)
