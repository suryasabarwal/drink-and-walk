"""City search (Open-Meteo, free, no key) and address search (Nominatim, free, 1 request a second)."""
from __future__ import annotations

from typing import Any

from .. import config
from . import SourceDown
from .http import session, throttle


def search_cities(query: str, count: int = 6) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    try:
        r = session.get(
            config.GEOCODE_URL,
            params={"name": q[:60], "count": count, "language": "en", "format": "json"},
            timeout=config.HTTP_TIMEOUT,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
    except (OSError, ValueError) as exc:
        raise SourceDown(f"city search: {type(exc).__name__}") from exc
    out = []
    for c in results:
        label = ", ".join(x for x in (c.get("name"), c.get("admin1"), c.get("country_code")) if x)
        out.append(
            {
                "label": label,
                "name": c.get("name"),
                "lat": c["latitude"],
                "lon": c["longitude"],
                "country": c.get("country_code", ""),
                "timezone": c.get("timezone", ""),
                "population": c.get("population", 0),
            }
        )
    return out


def locate(query: str, near_lat: float, near_lon: float) -> list[dict[str, Any]]:
    """Find a hotel or street address close to the chosen city. Called on submit, never while typing."""
    q = (query or "").strip()
    if len(q) < 3:
        return []
    d = 0.35  # roughly 35 km box around the city center
    box = f"{near_lon - d},{near_lat + d},{near_lon + d},{near_lat - d}"
    try:
        throttle("nominatim", 1.1)
        r = session.get(
            config.NOMINATIM_URL,
            params={"q": q[:120], "format": "jsonv2", "limit": 5, "viewbox": box, "bounded": 1},
            timeout=config.HTTP_TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()
    except (OSError, ValueError) as exc:
        raise SourceDown(f"address search: {type(exc).__name__}") from exc
    return [
        {"label": row.get("display_name", "")[:140], "lat": float(row["lat"]), "lon": float(row["lon"])}
        for row in rows
        if "lat" in row and "lon" in row
    ]
