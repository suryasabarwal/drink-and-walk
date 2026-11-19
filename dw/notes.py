"""Heads-up banners: holidays (US), weekends, and weather. Only says what it can back up."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def us_holidays(year: int) -> dict[date, tuple[str, str]]:
    """date -> (name, kind). kind 'party' means crowds and covers, 'quiet' means places close."""
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return {
        date(year, 1, 1): ("New Year's Day", "quiet"),
        date(year, 3, 17): ("St. Patrick's Day", "party"),
        date(year, 5, 5): ("Cinco de Mayo", "party"),
        _last_weekday(year, 5, 0): ("Memorial Day", "long"),
        date(year, 7, 4): ("the Fourth of July", "party"),
        _nth_weekday(year, 9, 0, 1): ("Labor Day", "long"),
        date(year, 10, 31): ("Halloween", "party"),
        thanksgiving - timedelta(days=1): ("the night before Thanksgiving", "party"),
        thanksgiving: ("Thanksgiving", "quiet"),
        date(year, 12, 24): ("Christmas Eve", "quiet"),
        date(year, 12, 25): ("Christmas Day", "quiet"),
        date(year, 12, 31): ("New Year's Eve", "party"),
    }


def _holiday_text(name: str, kind: str) -> str:
    if kind == "party":
        return f"{name[0].upper() + name[1:]} is a big night out. Expect lines, cover charges and higher prices."
    if kind == "quiet":
        return f"{name} means many bars and restaurants close early or all day. Check hours before you plan around a place."
    return f"{name} weekend. Expect crowds and some higher prices."


def banners(dates: list[date], country: str, weather: dict[str, dict[str, Any]] | None) -> list[dict[str, str]]:
    """weather is None when the forecast should exist but could not be fetched."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(level: str, text: str) -> None:
        if text not in seen:
            seen.add(text)
            out.append({"level": level, "text": text})

    if country.upper() == "US":
        hol = {}
        for y in {d.year for d in dates} | {dates[-1].year}:
            hol.update(us_holidays(y))
        for d in dates:
            if d in hol:
                name, kind = hol[d]
                add("warn", _holiday_text(name, kind))
            else:
                # Friday to Sunday before a Monday holiday
                for k in range(1, 4):
                    mon = d + timedelta(days=k)
                    if mon in hol and hol[mon][1] == "long" and mon.weekday() == 0:
                        add("warn", _holiday_text(hol[mon][0], "long"))
    if any(d.weekday() in (4, 5) for d in dates):
        add("info", "Friday and Saturday nights cost more. Many happy hours are weekday only, so ask before you assume.")
    if weather is None:
        add("info", "Could not reach the weather forecast just now. Check one before you head out.")
        weather = {}
    for d in dates:
        w = weather.get(d.isoformat())
        if not w:
            continue
        if (w.get("rain_pct") or 0) >= 50:
            add("info", f"Rain looks likely on {d:%a %b} {d.day} ({w['rain_pct']}%). Bring a jacket and favor places with indoor seating.")
        elif w.get("rain_pct") is None and (w.get("rain_mm") or 0) >= 1:
            add("info", f"Rain expected on the evening of {d:%a %b} {d.day} (about {w['rain_mm']:g} mm). Bring a jacket and favor places with indoor seating.")
        if w.get("lo_c") is not None and w["lo_c"] <= 0:
            add("info", f"It gets below freezing on {d:%a %b} {d.day}. Short walks between stops help.")
        if w.get("hi_c") is not None and w["hi_c"] >= 33:
            add("info", f"Hot on {d:%a %b} {d.day}. Carry water and take the shaded side of the street.")
    if dates and (dates[0] - date.today()).days > 15:
        add("info", "The weather forecast only reaches about two weeks out. Check back closer to the trip.")
    return out
