"""Builds the night: picks stops in time order, each one close to the last, cheapest first.

How a stop is chosen: every place is scored on estimated price, how well it fits the vibe,
whether a community deal or a map-listed happy hour exists, whether it is open then, and how far
it is from the previous stop. Expensive cocktail-style places are left out. The best few
runners-up are kept as swap options.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import geo, voice
from .places import DRINK_AMENITIES, TICKETED, open_state

FOOD_ROLE = {"restaurant", "fast_food", "food_court"}
TIER_BONUS = {"cheap": 0.5, "ok": 0.15, "pricey": -9.0}
# The "last one" stop is one round, not two, so it counts for half.
COST_FACTOR = {"last": 0.5}
# Over budget: the last round goes first, then the optional late bite, then the breather.
TRIM_ORDER = ["last", "late", "breather"]


def stop_cost(slot: str, place: dict[str, Any]) -> tuple[int, int, int]:
    f = COST_FACTOR.get(slot, 1.0)
    pr = place["price"]
    return round(pr["mid"] * f), round(pr["low"] * f), round(pr["high"] * f)


def fmt_time(minute: int) -> str:
    m = minute % 1440
    h, mm = divmod(m, 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{mm:02d} {suffix}"


def slots_for(weekday: int, vibe: str, live_music: bool, late_night: bool) -> list[dict[str, Any]]:
    if weekday <= 4:  # Mon to Fri: happy hour first, then dinner
        slots = [("happy", 17 * 60, "drink"), ("eat", 18 * 60 + 30, "eat")]
    else:
        slots = [("eat", 17 * 60 + 30, "eat"), ("happy", 19 * 60, "drink")]
    if vibe == "dive":
        slots += [("dive", 20 * 60 + 45, "drink"), ("last", 22 * 60 + 30, "drink")]
    elif vibe == "chill":
        slots += [("breather", 20 * 60 + 30, "breather"), ("last", 22 * 60, "chilldrink")]
    else:
        slots += [("lively", 21 * 60, "drink"), ("last", 22 * 60 + 45, "drink")]
    if live_music:
        # swap the main stop for a music stop
        idx = next(i for i, s in enumerate(slots) if s[0] in ("dive", "lively", "breather"))
        if vibe == "chill":
            idx = len(slots) - 1
        slots[idx] = ("music", slots[idx][1], "music")
    if late_night:
        slots.append(("late", 24 * 60 + 15, "late"))
    return [{"key": k, "minute": m, "role": r} for k, m, r in slots]


def _role_ok(place: dict[str, Any], role: str, vibe: str, free_only: bool) -> bool:
    a = place["amenity"]
    if free_only and place["ticketed"]:
        return False
    if role == "drink":
        return a in DRINK_AMENITIES
    if role == "music":
        return place["live_music"] and (a in DRINK_AMENITIES or a == "music_venue")
    if role == "eat" or role == "late":
        return a in FOOD_ROLE
    if role == "breather":
        return a == "cafe" or (a in DRINK_AMENITIES and place["vibe"]["chill"] >= 0.4)
    if role == "chilldrink":
        return a in DRINK_AMENITIES and place["vibe"]["chill"] >= 0.25
    return False


def rating_bonus(place: dict[str, Any]) -> float:
    """Cheap is the point, but not a place people hate. Only counts with enough reviews."""
    r, n = place.get("rating"), place.get("rating_count") or 0
    if r is None or n < 15:
        return 0.0
    if r < 3.5:
        return -0.6
    return max(-0.2, min(0.3, (r - 4.0) * 0.35))


def _score(place, slot, prev, vibe, ctx, night, max_leg) -> tuple[float, bool | None, float] | None:
    role = slot["role"]
    if not _role_ok(place, role, vibe, ctx["free_only"]):
        return None
    tier = place["price"]["tier"]
    if tier == "pricey" and not ctx["allow_pricey"]:
        return None
    pid = place["id"]
    if pid in night["used"]:
        return None
    dist = geo.haversine_m(prev[0], prev[1], place["lat"], place["lon"])
    if dist > max_leg:
        return None
    state = open_state(place, night["weekday"], slot["minute"])
    if state is False:
        return None
    if role == "late" and state is not True:
        return None
    s = 1.0 + TIER_BONUS[tier] - place["price"]["mid"] / 100
    if role in ("drink", "music", "chilldrink", "breather"):
        s += 0.5 * place["vibe"][vibe]
    if ctx["deals"].get(pid):
        s += 0.6
    if place.get("happy_hint") and slot["key"] == "happy":
        s += 0.4
    if ctx["free_only"] and place["no_cover"]:
        s += 0.2
    if state is None:
        s -= 0.2
    if place.get("website"):
        s += 0.03
    s += rating_bonus(place)
    if pid in ctx["used_other_nights"]:
        s -= 1.0
    s -= 0.9 * dist / 1000
    return s, state, dist


def _stop_view(place, slot, state, dist, ctx, vibe) -> dict[str, Any]:
    key = slot["key"]
    if key in ("dive", "lively"):
        key_group = vibe if vibe in ("dive", "lively") else key
    else:
        key_group = key
    return {
        "slot": key,
        "label": voice.SLOT_LABELS[key],
        "minute": slot["minute"],
        "time": fmt_time(slot["minute"]),
        "place": place,
        "cost": stop_cost(key, place)[0],
        "open": state,
        "line": voice.pick(key_group if key_group in voice.LINES else key, place["id"] + key),
        "deals": ctx["deals"].get(place["id"], []),
        "from_stay_m": None,
        "long_walk": dist > 1500,
    }


def build_night(places, stay, day: date, vibe, ctx, used_other_nights) -> dict[str, Any]:
    night = {"weekday": day.weekday(), "used": set()}
    ctx = {**ctx, "used_other_nights": used_other_nights}
    prev = (stay["lat"], stay["lon"])
    stops: list[dict[str, Any]] = []
    missing: list[str] = []
    for slot in slots_for(day.weekday(), vibe, ctx["live_music"], ctx["late_night"]):
        chosen = None
        for cap in (1500, 3500):
            scored = []
            for p in places:
                r = _score(p, slot, prev, vibe, ctx, night, cap)
                if r:
                    scored.append((r[0], r[1], r[2], p))
            if not scored and ctx["allow_pricey_fallback"]:
                ctx2 = {**ctx, "allow_pricey": True}
                for p in places:
                    r = _score(p, slot, prev, vibe, ctx2, night, cap)
                    if r:
                        scored.append((r[0], r[1], r[2], p))
            if scored:
                scored.sort(key=lambda t: -t[0])
                chosen = scored
                break
        if not chosen:
            missing.append(slot["key"])
            continue
        best = chosen[0]
        stop = _stop_view(best[3], slot, best[1], best[2], ctx, vibe)
        stop["alternatives"] = [_stop_view(a[3], slot, a[1], a[2], ctx, vibe) for a in chosen[1:10]]
        for alt in stop["alternatives"]:
            alt.pop("alternatives", None)
        stops.append(stop)
        night["used"].add(best[3]["id"])
        prev = (best[3]["lat"], best[3]["lon"])
    # A runner-up for one slot must not be a place already used in another slot tonight.
    chosen_ids = {s["place"]["id"] for s in stops}
    chosen_names = {s["place"]["name"].lower() for s in stops}
    for s in stops:
        alts, names = [], set(chosen_names)
        for a in s["alternatives"]:
            nm = a["place"]["name"].lower()
            if a["place"]["id"] in chosen_ids or nm in names:
                continue  # also skips a second branch of the same chain
            names.add(nm)
            alts.append(a)
        s["alternatives"] = alts
    return {"date": day.isoformat(), "weekday": day.strftime("%a"), "stops": stops, "missing": missing}


def build_plan(places, stay, days: list[date], people, budget_pp, vibe, live_music, late_night, free_only, deals, events):
    ctx = {
        "live_music": live_music,
        "late_night": late_night,
        "free_only": free_only,
        "deals": deals,
        "allow_pricey": False,
        "allow_pricey_fallback": True,
    }
    nights, used_all = [], set()
    for d in days:
        n = build_night(places, stay, d, vibe, ctx, set(used_all))
        used_all |= {s["place"]["id"] for s in n["stops"]}
        n["events"] = [e for e in events if e.get("date") == d.isoformat()]
        n["tips"] = []
        # Over budget? Drop the optional stops first, and say so.
        while sum(s["cost"] for s in n["stops"]) > budget_pp:
            victim = next((s for k in TRIM_ORDER for s in n["stops"] if s["slot"] == k), None)
            if victim is None:
                break
            n["stops"].remove(victim)
            n["tips"].append(f"Dropped the {victim['label'].lower()} to stay near your ${round(budget_pp)} limit. Raise the limit to bring it back.")
        if live_music and "music" in n["missing"]:
            n["tips"].append(voice.UI["no_live"])
        if late_night and "late" in n["missing"]:
            n["tips"].append(voice.UI["no_late"])
        nights.append(n)
    plan = {
        "stay": stay,
        "people": people,
        "budget_pp": budget_pp,
        "vibe": vibe,
        "nights": nights,
        "thin": len(places) < 12,
        "place_count": len(places),
    }
    return finalize(plan)


def finalize(plan: dict[str, Any]) -> dict[str, Any]:
    """Recompute walking legs, costs and the budget meter. Used after building and after a swap."""
    stay = plan["stay"]
    people = plan["people"]
    budget = float(plan["budget_pp"])
    for n in plan["nights"]:
        prev = (stay["lat"], stay["lon"])
        prev_name = stay.get("name") or "where you're staying"
        legs, spent, low, high = [], 0, 0, 0
        for s in n["stops"]:
            p = s["place"]
            dist = geo.haversine_m(prev[0], prev[1], p["lat"], p["lon"])
            legs.append({"from": prev_name, "to": p["name"], "min": geo.walk_minutes(dist), "label": geo.walk_km_label(dist), "m": round(dist)})
            c, lo, hi = stop_cost(s["slot"], p)
            s["cost"] = c
            spent += c
            low += lo
            high += hi
            prev, prev_name = (p["lat"], p["lon"]), p["name"]
        home = None
        if n["stops"]:
            dist = geo.haversine_m(prev[0], prev[1], stay["lat"], stay["lon"])
            home = {"min": geo.walk_minutes(dist), "label": geo.walk_km_label(dist), "m": round(dist)}
        n["legs"] = legs
        n["home"] = home
        pct = spent / budget if budget else 0
        if spent == 0:
            state, msg = "under", "Nothing planned yet."
        elif pct <= 0.85:
            state, msg = "under", f"About ${round(budget - spent)} under your limit."
        elif pct <= 1.0:
            state, msg = "near", "Right at your limit. Skip a round if anything runs over."
        else:
            state, msg = "over", f"About ${round(spent - budget)} over. Swap a stop for a cheaper one or skip the last round."
        n["totals"] = {
            "per_person": spent,
            "range": [low, high],
            "group": spent * people,
            "pct": round(min(pct, 1.6), 2),
            "state": state,
            "message": msg,
        }
    return plan


def _late_confirmed(place, day: int, minute: int) -> bool:
    """Open now and confirmed open past 11:30 pm tonight (or for another hour, if it is already late)."""
    tonight_late = 23 * 60 + 30
    if minute < 5 * 60:  # after midnight counts as the night before
        day, minute = (day - 1) % 7, minute + 1440
    if open_state(place, day, minute, span=30) is not True:
        return False
    return open_state(place, day, max(minute, tonight_late), span=60) is True


def nearby(places, lat, lon, day: int, minute: int, mode: str, deals, limit=14, radius=1200) -> list[dict[str, Any]]:
    out = []
    for p in places:
        a = p["amenity"]
        if mode == "drink" and a not in DRINK_AMENITIES:
            continue
        if mode == "eat" and a not in FOOD_ROLE | {"cafe"}:
            continue
        if mode == "music" and not p["live_music"]:
            continue
        if mode == "free" and (p["ticketed"] or not (p["no_cover"] or p["live_music"] or p["price"]["tier"] == "cheap")):
            continue
        if mode == "late" and a not in FOOD_ROLE:
            continue
        if p["price"]["tier"] == "pricey":
            continue
        dist = geo.haversine_m(lat, lon, p["lat"], p["lon"])
        if dist > radius:
            continue
        state = open_state(p, day, minute, span=30)
        if state is False:
            continue
        if mode == "late" and not _late_confirmed(p, day, minute):
            continue
        score = TIER_BONUS[p["price"]["tier"]] + rating_bonus(p) - 1.2 * dist / 1000 + (0.6 if deals.get(p["id"]) else 0) - (0.2 if state is None else 0)
        out.append((score, p, dist, state))
    out.sort(key=lambda t: -t[0])
    return [
        {
            "place": p,
            "cost": p["price"]["mid"],
            "open": state,
            "walk": {"min": geo.walk_minutes(dist), "label": geo.walk_km_label(dist), "m": round(dist)},
            "deals": deals.get(p["id"], []),
        }
        for _, p, dist, state in out[:limit]
    ]


# ---- cleaning posted data -------------------------------------------------

_ID = re.compile(r"^([nwr]\d{1,12}|g:[A-Za-z0-9_-]{6,200})$")


def _s(v: Any, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v or ""))[:n]


def _num(v: Any, lo: float, hi: float, default: float = 0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def clean_place(p: dict[str, Any]) -> dict[str, Any]:
    price = p.get("price") or {}
    site = _s(p.get("website"), 200)
    gm = _s(p.get("gmaps"), 300)
    return {
        "id": p.get("id") if _ID.match(str(p.get("id", ""))) else "n0",
        "name": _s(p.get("name"), 80) or "Stop",
        "lat": _num(p.get("lat"), -90, 90),
        "lon": _num(p.get("lon"), -180, 180),
        "amenity": _s(p.get("amenity"), 20),
        "address": _s(p.get("address"), 80),
        "website": site if site.startswith(("http://", "https://")) else "",
        "gmaps": gm if gm.startswith(("https://maps.google.com/", "https://www.google.com/maps")) else "",
        "live_music": bool(p.get("live_music")),
        "price": {
            "low": int(_num(price.get("low"), 0, 500)),
            "high": int(_num(price.get("high"), 0, 500)),
            "mid": int(_num(price.get("mid"), 0, 500)),
            "tier": price.get("tier") if price.get("tier") in TIER_BONUS else "ok",
        },
    }


def clean_plan(raw: dict[str, Any]) -> dict[str, Any]:
    stay = raw.get("stay") or {}
    plan = {
        "stay": {"lat": _num(stay.get("lat"), -90, 90), "lon": _num(stay.get("lon"), -180, 180), "name": _s(stay.get("name"), 80)},
        "people": int(_num(raw.get("people"), 1, 20, 2)),
        "budget_pp": _num(raw.get("budget_pp"), 5, 500, 40),
        "vibe": raw.get("vibe") if raw.get("vibe") in ("dive", "chill", "lively") else "dive",
        "city": _s(raw.get("city"), 80),
        "nights": [],
    }
    for n in (raw.get("nights") or [])[:4]:
        try:
            d = date.fromisoformat(str(n.get("date")))
        except ValueError:
            continue
        stops = []
        for s in (n.get("stops") or [])[:8]:
            key = s.get("slot") if s.get("slot") in voice.SLOT_LABELS else "dive"
            minute = int(_num(s.get("minute"), 0, 2000, 1200))
            stops.append(
                {
                    "slot": key,
                    "label": voice.SLOT_LABELS[key],
                    "minute": minute,
                    "time": fmt_time(minute),
                    "place": clean_place(s.get("place") or {}),
                    "open": s.get("open") if s.get("open") in (True, False) else None,
                    "line": _s(s.get("line"), 160),
                    "deals": [],
                }
            )
        plan["nights"].append({"date": d.isoformat(), "weekday": d.strftime("%a"), "stops": stops, "missing": [], "tips": [], "events": []})
    return plan
