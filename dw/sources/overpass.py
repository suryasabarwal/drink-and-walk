"""Bars, pubs and food from OpenStreetMap through the public Overpass API (free, no key).

The public servers ask for light use, so this:
  * snaps requests to a grid and caches the answer for a week, so nearby searches share one query
  * counts real queries against a daily budget shared by all visitors
  * tries a backup server if the first one fails
  * falls back to an older cached answer if every server is down
"""
from __future__ import annotations

import json
import time
from typing import Any

from .. import config, geo
from . import SourceDown
from .http import session, take_quota, throttle

GRID = 0.005  # about 550 m


def build_query(lat: float, lon: float, radius: int) -> str:
    around = f"(around:{radius},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:25];\n"
        f'(nwr["amenity"~"^(bar|pub|biergarten|music_venue)$"]["name"]{around};)->.drinks;\n'
        ".drinks out center tags 400;\n"
        f'(nwr["amenity"~"^(restaurant|fast_food|cafe|food_court)$"]["name"]{around};)->.food;\n'
        ".food out center tags 500;\n"
    )


def _snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 4)


def _cache_path(lat: float, lon: float, radius: int):
    return config.CACHE_DIR / f"places_{lat:.4f}_{lon:.4f}_{radius}.json"


def _read_cache(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_cache(path, elements):
    try:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched": time.time(), "elements": elements}))
    except OSError:
        pass


def _run(path, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cached = _read_cache(path)
    max_age = config.PLACES_CACHE_DAYS * 86400
    if cached and time.time() - cached["fetched"] < max_age:
        return cached["elements"], {"source": "cache", "age_hours": round((time.time() - cached["fetched"]) / 3600)}

    error = "no servers tried"
    if take_quota("overpass", config.OVERPASS_DAILY_LIMIT):
        for url in config.OVERPASS_SERVERS:
            try:
                throttle("overpass", 1.0)
                r = session.post(url, data={"data": query}, timeout=config.HTTP_TIMEOUT)
                if r.status_code == 200:
                    elements = r.json().get("elements", [])
                    _write_cache(path, elements)
                    return elements, {"source": "live", "server": url.split("/")[2]}
                error = f"{url.split('/')[2]} answered {r.status_code}"
            except (OSError, ValueError) as exc:  # requests errors are OSError subclasses
                error = f"{url.split('/')[2]}: {type(exc).__name__}"
    else:
        error = "daily map-data budget used up"

    if cached:
        return cached["elements"], {
            "source": "stale-cache",
            "age_hours": round((time.time() - cached["fetched"]) / 3600),
            "warning": error,
        }
    raise SourceDown(error)


def fetch_elements(lat: float, lon: float, radius: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (elements, meta). meta says whether this came from cache and how old it is."""
    radius = max(300, min(int(radius), config.MAX_RADIUS_M))
    slat, slon = _snap(lat), _snap(lon)
    big = radius + 600  # extra reach so one cached query covers nearby start points
    return _run(_cache_path(slat, slon, big), build_query(slat, slon, big))


def anchors_query(lat: float, lon: float) -> str:
    return (
        "[out:json][timeout:25];\n"
        "(\n"
        f'nwr["place"~"^(suburb|neighbourhood|quarter)$"]["name"](around:5000,{lat:.4f},{lon:.4f});\n'
        f'nwr["railway"="station"]["name"](around:6000,{lat:.4f},{lon:.4f});\n'
        f'nwr["amenity"="bus_station"]["name"](around:6000,{lat:.4f},{lon:.4f});\n'
        ");\nout center tags 120;\n"
    )


def fetch_anchors(lat: float, lon: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Neighborhoods and stations near a city center, as starting points."""
    slat, slon = round(lat, 2), round(lon, 2)
    path = config.CACHE_DIR / f"anchors_{slat:.2f}_{slon:.2f}.json"
    elements, meta = _run(path, anchors_query(slat, slon))
    out, seen = [], set()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        c = el if el.get("type") == "node" else (el.get("center") or {})
        if not name or "lat" not in c or name.lower() in seen:
            continue
        seen.add(name.lower())
        if "place" in tags:
            kind = "Neighborhood"
        elif tags.get("amenity") == "bus_station":
            kind = "Bus station"
        else:
            kind = "Train station"
        out.append({"name": name[:60], "kind": kind, "lat": c["lat"], "lon": c["lon"], "d": geo.haversine_m(lat, lon, c["lat"], c["lon"])})
    out.sort(key=lambda a: a["d"])
    hoods = [a for a in out if a["kind"] == "Neighborhood"][:14]
    stations = [a for a in out if a["kind"] != "Neighborhood"][:6]
    for a in hoods + stations:
        a.pop("d")
    return hoods + stations, meta


def elements_near(lat: float, lon: float, radius: int):
    """Elements trimmed to the true radius around the real point."""
    from ..places import from_elements

    elements, meta = fetch_elements(lat, lon, radius)
    places = from_elements(elements)
    near = [p for p in places if geo.haversine_m(lat, lon, p["lat"], p["lon"]) <= radius]
    return near, meta
