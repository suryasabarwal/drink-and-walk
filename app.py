"""Drink and Walk: web app. Run with `python app.py` or `gunicorn app:app`."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import date, timedelta
from functools import wraps

from flask import Flask, Response, jsonify, render_template, request

from dw import config, deals as deal_board, export, notes, planner, voice
from dw.sources import SourceDown, geocode, google_places, overpass, ticketmaster, weather

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200_000

# ---- tiny per-visitor rate limit (in memory) -------------------------------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def limited(name: str, per_minute: int):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")).split(",")[0].strip()
            q, now = _hits[(name, ip)], time.monotonic()
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= per_minute:
                return jsonify(error="Slow down a little and try again in a minute."), 429
            q.append(now)
            return fn(*a, **kw)
        return wrapper
    return deco


@app.errorhandler(SourceDown)
def _source_down(exc):
    what = "City search" if str(exc).startswith("city search") else "Address search" if str(exc).startswith("address search") else "The free map data"
    return jsonify(error=f"{what} is busy or unreachable right now. Try again in a minute.", detail=str(exc)), 503


@app.after_request
def _headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


def _float(name, lo, hi, source=None):
    src = source if source is not None else request.args
    try:
        v = float(src.get(name))
    except (TypeError, ValueError):
        raise ValueError(f"{name} is missing or not a number")
    if not lo <= v <= hi:
        raise ValueError(f"{name} is out of range")
    return v


@app.errorhandler(ValueError)
def _bad(exc):
    return jsonify(error=str(exc)), 400


@app.get("/")
def index():
    return render_template("index.html", ticketmaster=ticketmaster.enabled())


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/api/cities")
@limited("cities", 60)
def cities():
    return jsonify(results=geocode.search_cities(request.args.get("q", "")))


@app.get("/api/locate")
@limited("locate", 12)
def locate():
    lat, lon = _float("lat", -90, 90), _float("lon", -180, 180)
    return jsonify(results=geocode.locate(request.args.get("q", ""), lat, lon))


@app.get("/api/anchors")
@limited("anchors", 20)
def anchors():
    lat, lon = _float("lat", -90, 90), _float("lon", -180, 180)
    items, meta = overpass.fetch_anchors(lat, lon)
    return jsonify(results=items, meta=meta)


def _parse_plan_request(j: dict):
    try:
        start = date.fromisoformat(str(j.get("start")))
        end = date.fromisoformat(str(j.get("end") or j.get("start")))
    except ValueError:
        raise ValueError("Pick your dates first.")
    if end < start:
        raise ValueError("The end date is before the start date.")
    nights = (end - start).days + 1
    if nights > config.MAX_NIGHTS:
        raise ValueError(f"Keep it to {config.MAX_NIGHTS} nights or fewer.")
    if start < date.today() - timedelta(days=1):
        raise ValueError("That date has already passed.")
    stay = j.get("stay") or {}
    city = j.get("city") or {}
    people = int(_float("people", 1, config.MAX_PEOPLE, j))
    budget = _float("budget_pp", 5, 300, j)
    vibe = j.get("vibe") if j.get("vibe") in ("dive", "chill", "lively") else "dive"
    return {
        "days": [start + timedelta(days=i) for i in range(nights)],
        "stay": {"lat": _float("lat", -90, 90, stay), "lon": _float("lon", -180, 180, stay), "name": str(stay.get("name") or "")[:80] or "the city center"},
        "city": {"name": str(city.get("name") or "")[:80], "country": str(city.get("country") or "")[:2].upper()},
        "people": people,
        "budget": budget,
        "vibe": vibe,
        "live": bool(j.get("live_music")),
        "late": bool(j.get("late_night")),
        "free": bool(j.get("free_only")),
        "radius": int(max(500, min(float(j.get("radius") or config.DEFAULT_RADIUS_M), config.MAX_RADIUS_M))),
    }


def get_places(lat: float, lon: float, radius: int, want_live: bool = False, want_late: bool = False):
    """Google Places when a key is set (best data), else OpenStreetMap. Falls back to the open map
    if Google fails, and says so in meta."""
    if google_places.enabled():
        try:
            return google_places.places_near(lat, lon, radius, want_live, want_late)
        except SourceDown as exc:
            places, meta = overpass.elements_near(lat, lon, radius)
            return places, {**meta, "fallback_from": str(exc)}
    return overpass.elements_near(lat, lon, radius)


def _attach_text(plan):
    plan["text"] = export.to_text(plan)
    return plan


@app.post("/api/plan")
@limited("plan", 10)
def make_plan():
    r = _parse_plan_request(request.get_json(silent=True) or {})
    places, meta = get_places(r["stay"]["lat"], r["stay"]["lon"], r["radius"], r["live"], r["late"])
    deals = deal_board.for_places({p["id"] for p in places})
    wx = weather.forecast(r["stay"]["lat"], r["stay"]["lon"], r["days"][0], r["days"][-1])
    events = ticketmaster.events(r["stay"]["lat"], r["stay"]["lon"], r["days"][0], r["days"][-1])
    plan = planner.build_plan(
        places, r["stay"], r["days"], r["people"], r["budget"], r["vibe"], r["live"], r["late"], r["free"], deals, events
    )
    plan["city"] = r["city"]["name"]
    plan["country"] = r["city"]["country"]
    plan["radius"] = r["radius"]
    plan["source"] = {**meta, **({"weather": weather.last_error} if wx is None else {})}
    plan["google"] = meta.get("source") == "google"
    plan["banners"] = notes.banners(r["days"], r["city"]["country"], wx)
    plan["safety"] = voice.UI["safety"] if r["city"]["country"] == "US" else voice.UI["safety"][:3]
    plan["events_enabled"] = ticketmaster.enabled()
    for n in plan["nights"]:
        n["weather"] = (wx or {}).get(n["date"])
    return jsonify(_attach_text(plan))


@app.post("/api/recompute")
@limited("recompute", 60)
def recompute():
    raw = (request.get_json(silent=True) or {}).get("plan") or {}
    plan = planner.finalize(planner.clean_plan(raw))
    return jsonify(text=export.to_text(plan), nights=[{"legs": n["legs"], "home": n["home"], "totals": n["totals"]} for n in plan["nights"]])


@app.post("/api/ics")
@limited("ics", 20)
def ics():
    raw = (request.get_json(silent=True) or {}).get("plan") or {}
    plan = planner.finalize(planner.clean_plan(raw))
    if not any(n["stops"] for n in plan["nights"]):
        raise ValueError("There is nothing in the plan to add to a calendar.")
    return Response(export.to_ics(plan), mimetype="text/calendar", headers={"Content-Disposition": "attachment; filename=drink-and-walk.ics"})


@app.get("/api/nearby")
@limited("nearby", 20)
def nearby():
    lat, lon = _float("lat", -90, 90), _float("lon", -180, 180)
    day = int(_float("day", 0, 6))
    minute = int(_float("minute", 0, 1439))
    mode = request.args.get("mode", "drink")
    if mode not in ("drink", "eat", "music", "free", "late"):
        raise ValueError("unknown mode")
    places, meta = get_places(lat, lon, 1200, mode == "music", mode == "late")
    deals = deal_board.for_places({p["id"] for p in places})
    return jsonify(results=planner.nearby(places, lat, lon, day, minute, mode, deals), meta=meta, total_known=len(places), google=meta.get("source") == "google")


@app.post("/api/deals")
@limited("deals", 5)
def add_deal():
    j = request.get_json(silent=True) or {}
    try:
        d = deal_board.add(j.get("place_id"), j.get("place_name"), j.get("text"), j.get("when", ""))
    except deal_board.DealError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(deal={"id": d["id"], "text": d["text"], "when": d["when"], "days_old": 0}), 201


@app.post("/api/deals/<deal_id>/gone")
@limited("deal_gone", 10)
def deal_gone(deal_id):
    return jsonify(ok=deal_board.report_gone(deal_id[:20]))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
