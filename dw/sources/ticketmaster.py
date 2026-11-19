"""Optional: concerts and festivals from Ticketmaster Discovery (free key, 5,000 calls a day).

Without TICKETMASTER_KEY this returns nothing and the app says so instead of making things up.
Ticketmaster allows about 2 requests a second, so calls are spaced out.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config
from .http import session, take_quota, throttle


def enabled() -> bool:
    return bool(config.TICKETMASTER_KEY)


def events(lat: float, lon: float, start: date, end: date) -> list[dict[str, Any]]:
    if not enabled():
        return []
    out: dict[str, dict[str, Any]] = {}
    for extra in ({"classificationName": "music"}, {"keyword": "festival"}):
        if not take_quota("ticketmaster", 2000):
            break
        try:
            throttle("ticketmaster", 0.6)
            r = session.get(
                config.TICKETMASTER_URL,
                params={
                    "apikey": config.TICKETMASTER_KEY,
                    "latlong": f"{lat:.4f},{lon:.4f}",
                    "radius": 6,
                    "unit": "miles",
                    "startDateTime": f"{start.isoformat()}T00:00:00Z",
                    "endDateTime": f"{end.isoformat()}T23:59:59Z",
                    "size": 20,
                    "sort": "date,asc",
                    **extra,
                },
                timeout=config.HTTP_TIMEOUT,
            )
            r.raise_for_status()
            items = (r.json().get("_embedded") or {}).get("events", [])
        except (OSError, ValueError):
            continue
        for e in items:
            dates = (e.get("dates") or {}).get("start") or {}
            venue = (((e.get("_embedded") or {}).get("venues")) or [{}])[0]
            pr = (e.get("priceRanges") or [{}])[0]
            price = pr.get("min")
            out[e["id"]] = {
                "id": e["id"],
                "name": e.get("name", "")[:100],
                "date": dates.get("localDate", ""),
                "time": (dates.get("localTime") or "")[:5],
                "venue": venue.get("name", "")[:80],
                "price_from": price,
                "currency": str(pr.get("currency") or "")[:3].upper(),
                "url": e.get("url", ""),
            }
    return sorted(out.values(), key=lambda x: (x["date"], x["time"]))
