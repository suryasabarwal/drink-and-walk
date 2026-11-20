"""City search (Open-Meteo, free, no key) and address search (Nominatim, free, 1 request a second)."""
from __future__ import annotations

from typing import Any

from .. import config, money
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
        cur = money.for_country(c.get("country_code")) or money.USD
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
                "currency": cur.as_dict(),
                "budget": money.budget_choices(cur),
            }
        )
    return out


def find_place(query: str) -> list[dict[str, Any]]:
    """Any neighborhood, street or landmark, worldwide, from Nominatim. On submit only, 1 a second."""
    q = (query or "").strip()
    if len(q) < 3:
        return []
    try:
        throttle("nominatim", 1.1)
        r = session.get(config.NOMINATIM_URL, params={"q": q[:120], "format": "jsonv2", "limit": 6, "addressdetails": 1},
                        timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
    except (OSError, ValueError) as exc:
        raise SourceDown(f"address search: {type(exc).__name__}") from exc
    out = []
    for row in rows:
        if "lat" not in row or "lon" not in row:
            continue
        a = row.get("address") or {}
        name = (row.get("name") or row.get("display_name", "").split(",")[0]).strip()
        out.append({
            "label": name[:100],
            "sub": ", ".join(row.get("display_name", "").split(", ")[1:4])[:140],
            "lat": float(row["lat"]), "lon": float(row["lon"]),
            "country": (a.get("country_code") or "").upper()[:2],
            "town": (a.get("city") or a.get("town") or a.get("state_district") or a.get("state") or "")[:60],
        })
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
