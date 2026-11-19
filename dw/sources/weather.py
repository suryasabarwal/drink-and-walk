"""Forecast from Open-Meteo (free, about 16 days ahead)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config
from .http import session


def forecast(lat: float, lon: float, start: date, end: date) -> dict[str, dict[str, Any]]:
    """Return {iso_date: {hi_c, lo_c, rain_pct}}. Empty if out of range or the source is down."""
    today = date.today()
    if (start - today).days > 15 or end < today:
        return {}
    try:
        r = session.get(
            config.FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "start_date": max(start, today).isoformat(),
                "end_date": min(end, date.fromordinal(today.toordinal() + 15)).isoformat(),
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
        return out
    except (OSError, ValueError, KeyError, IndexError):
        return {}
