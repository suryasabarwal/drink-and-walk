"""Forecast from Open-Meteo (free, about 16 days ahead).

Open-Meteo's free tier has a daily request limit per IP, and free hosts share IPs, so answers are
kept for a few hours and reused by every plan near the same spot.
"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Any

from .. import config
from .http import session

CACHE_S = 3 * 3600
_cache: dict[tuple[float, float, str], tuple[float, dict[str, dict[str, Any]]]] = {}
_lock = threading.Lock()


def _fetch(lat: float, lon: float, today: date) -> dict[str, dict[str, Any]] | None:
    """The full 16 days for a spot, cached. None if the source failed."""
    key = (round(lat, 2), round(lon, 2), today.isoformat())
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
    try:
        r = session.get(
            config.FORECAST_URL,
            params={
                "latitude": key[0],
                "longitude": key[1],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=15)).isoformat(),
            },
            timeout=config.HTTP_TIMEOUT,
        )
        r.raise_for_status()
        d = r.json().get("daily", {})
        out = {}
        for i, day in enumerate(d.get("time", [])):
            out[day] = {
                "hi_c": d["temperature_2m_max"][i],
                "lo_c": d["temperature_2m_min"][i],
                "rain_pct": d["precipitation_probability_max"][i],
            }
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time(), out)
    return out


def forecast(lat: float, lon: float, start: date, end: date) -> dict[str, dict[str, Any]] | None:
    """{iso_date: {hi_c, lo_c, rain_pct}} for the trip.

    Empty when the trip is past the forecast range (nothing to know yet).
    None when the forecast should exist but the source could not be reached, so the app can say so.
    """
    today = date.today()
    if (start - today).days > 15 or end < today:
        return {}
    days = _fetch(lat, lon, today)
    if days is None:
        return None
    return {k: v for k, v in days.items() if start.isoformat() <= k <= end.isoformat()}
