"""Plain text for the group chat, and a calendar file (.ics).

The .ics helpers (_escape, _fold) are the same ones used in the rollover helper project.
Event times are "floating" local times: they show at 6:00 pm wherever the phone is.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any


def maps_link(p: dict[str, Any]) -> str:
    if p.get("gmaps"):
        return p["gmaps"]
    return f"https://www.google.com/maps/search/?api=1&query={p['lat']:.5f},{p['lon']:.5f}"


def to_text(plan: dict[str, Any]) -> str:
    people = plan["people"]
    lines = []
    for n in plan["nights"]:
        d = date.fromisoformat(n["date"])
        t = n["totals"]
        lines.append(f"DRINK AND WALK: {plan.get('city') or 'tonight'}")
        lines.append(f"{d:%a %b} {d.day}, {people} {'person' if people == 1 else 'people'}, about ${t['per_person']} each (${t['group']} total)")
        if plan["stay"].get("name"):
            lines.append(f"Starting from: {plan['stay']['name']}")
        lines.append("")
        for i, s in enumerate(n["stops"]):
            p = s["place"]
            leg = n["legs"][i]
            lines.append(f"{s['time']}  {s['label'].upper()}: {p['name']} (about ${s['cost']} each)")
            if p.get("address"):
                lines.append(f"   {p['address']}")
            lines.append(f"   {maps_link(p)}")
            lines.append(f"   walk {leg['min']} min from {leg['from']}")
            for dl in s.get("deals") or []:
                lines.append(f"   deal: {dl['text']}" + (f" ({dl['when']})" if dl.get("when") else ""))
        if n.get("home") and n["stops"]:
            h = n["home"]
            lines.append("")
            lines.append(f"Home: {h['min']} min walk, or book a ride before the last round.")
        lines.append("")
    lines.append("Prices are estimates. Call ahead to confirm hours and specials.")
    lines.append("Made with Drink and Walk. Map data from OpenStreetMap contributors.")
    return "\n".join(lines)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    out: list[str] = []
    current = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + part for part in out[1:]]


def to_ics(plan: dict[str, Any], now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//drink-and-walk//plan//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    count = 0
    for n in plan["nights"]:
        d = date.fromisoformat(n["date"])
        for i, s in enumerate(n["stops"]):
            p = s["place"]
            start = datetime(d.year, d.month, d.day) + timedelta(minutes=s["minute"])
            length = 60 if s["slot"] in ("eat", "late") else 75
            end = start + timedelta(minutes=length)
            uid = hashlib.sha1(f"{n['date']}{s['slot']}{p['id']}".encode()).hexdigest()[:16]
            desc = f"{s['label']}. About ${s['cost']} each (estimate). {maps_link(p)}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}@drink-and-walk.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{start:%Y%m%dT%H%M%S}",
                f"DTEND:{end:%Y%m%dT%H%M%S}",
                f"SUMMARY:{_escape(s['label'] + ': ' + p['name'])}",
                f"LOCATION:{_escape((p['name'] + ' ' + p.get('address', '')).strip())}",
                f"GEO:{p['lat']:.5f};{p['lon']:.5f}",
                f"DESCRIPTION:{_escape(desc)}",
            ]
            if i == 0:
                lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape('Drink and Walk starts soon')}", "TRIGGER:-PT45M", "END:VALARM"]
            lines.append("END:VEVENT")
            count += 1
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
