"""Forecast from Open-Meteo (free, about 16 days ahead), with MET Norway as a backup.

Open-Meteo's free tier has a daily request limit per IP, and free hosts share IPs, so it can say
no for the rest of the day. Then MET Norway (free, no key, about 9 days ahead, asks for a
User-Agent that names the app) fills in. Answers are kept for a few hours either way.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from .. import config
from .http import session

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
last_error = ""  # why the last fetch failed, for the plan's source notes

CACHE_S = 3 * 3600
_cache: dict[tuple[float, float, str], tuple[float, dict[str, dict[str, Any]]]] = {}
_lock = threading.Lock()


def _fetch(lat: float, lon: float, today: date) -> dict[str, dict[str, Any]] | None:
    """The forecast days for a spot, cached. None if every source failed."""
    global last_error
    key = (round(lat, 2), round(lon, 2), today.isoformat())
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
    out = _open_meteo(key[0], key[1], today)
    if out is None:
        out = _met_norway(key[0], key[1])
    if out is None:
        return None
    last_error = ""
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time(), out)
    return out


def _open_meteo(lat: float, lon: float, today: date) -> dict[str, dict[str, Any]] | None:
    global last_error
    key = (lat, lon)
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
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        last_error = f"open-meteo: {getattr(getattr(exc, 'response', None), 'status_code', '') or type(exc).__name__}"
        return None
    return out


def _met_norway(lat: float, lon: float) -> dict[str, dict[str, Any]] | None:
    """Hourly and 6 hourly points rolled up into days. MET gives rain amounts, not chances, so
    rain is reported in millimeters for the evening (4 pm to 2 am local), when people are out."""
    global last_error
    try:
        r = session.get(MET_URL, params={"lat": f"{lat:.2f}", "lon": f"{lon:.2f}"}, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        series = r.json()["properties"]["timeseries"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        last_error += f"; met.no: {getattr(getattr(exc, 'response', None), 'status_code', '') or type(exc).__name__}"
        return None
    offset = timedelta(hours=round(lon / 15))  # close enough to local time for a day boundary
    days: dict[str, dict[str, Any]] = {}
    for t in series:
        try:
            when = datetime.fromisoformat(t["time"].replace("Z", "+00:00")) + offset
            data = t["data"]
            temp = data["instant"]["details"]["air_temperature"]
        except (KeyError, ValueError):
            continue
        d = days.setdefault(when.date().isoformat(), {"hi_c": temp, "lo_c": temp, "rain_pct": None, "rain_mm": 0.0})
        d["hi_c"], d["lo_c"] = max(d["hi_c"], temp), min(d["lo_c"], temp)
        # the evening of a day runs past midnight, so 0 to 2 am counts for the day before
        evening_day = (when - timedelta(hours=2)).date().isoformat()
        hourly = (data.get("next_1_hours") or {}).get("details", {}).get("precipitation_amount")
        six = (data.get("next_6_hours") or {}).get("details", {}).get("precipitation_amount")
        if hourly is not None:
            if (when.hour >= 16 or when.hour < 2) and evening_day in days:
                days[evening_day]["rain_mm"] += hourly
        elif six is not None and 11 <= when.hour <= 20:
            # past about two days MET only gives 6 hour totals; count windows that touch the evening
            days[when.date().isoformat()]["rain_mm"] += six
    for d in days.values():
        d["rain_mm"] = round(d["rain_mm"], 1)
    return days or None


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
