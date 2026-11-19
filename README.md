# Drink and Walk

A cheap night out for friends splitting the bill. Pick a city, dates, group size, a budget and
where you are staying. Drink and Walk builds a walking route of cheap food, happy hours and live
music, in order, with walking times and a running cost.

Everything runs on free data. No accounts, no database, no API key required.

## What it does

- **Step-by-step flow.** One question per screen: city, dates, group and budget, starting point, mood.
- **Starts from where you sleep.** Hotel or address search, neighborhoods, train and bus stations,
  your location, or the city center. Every walk is measured from there.
- **Cheap by design.** Cocktail lounges, rooftop bars and wine bars are filtered out. Prices are
  estimates from the type of place, and the app labels them that way.
- **Walking order.** Each stop is chosen close to the one before, so you do not zigzag.
- **Swap this stop.** One tap brings the next best cheap option and updates walking times and costs.
  Undo is one tap too.
- **Budget meter.** If the night runs over your limit, the last round is dropped first and the app says so.
- **I'm out right now.** Skips planning. Shows cheap places open within walking distance.
- **Vibe dials.** Dive, chill or lively, plus live music, late-night food and free-stuff-only toggles.
- **Heads-up banners.** US holidays and long weekends, weekend pricing, rain, cold and heat.
- **Copy as text, add to calendar (.ics), share link.**
- **Deal board.** Visitors can add deals the map cannot know, like "$3 pints Tuesday".
  Deals show their age, can be reported as gone, and expire after six months.
- **Check Reddit** and **Map** links on every stop.

## Where the data comes from

| Need | Source | Cost |
| --- | --- | --- |
| City search | Open-Meteo geocoding | Free, no key |
| Bars, pubs, food, hours | OpenStreetMap via Overpass API | Free, no key |
| Hotel or address search | Nominatim (OpenStreetMap) | Free, 1 request a second |
| Weather | Open-Meteo forecast (about 16 days) | Free, no key |
| Concerts and festivals | Ticketmaster Discovery | Free key, optional |
| Deals | Visitors, stored in `data/deals.json` | Free |

What the app does not know, it says so. OpenStreetMap has no prices and almost no happy hour data,
so prices are estimates and happy hours are only shown when the map actually lists one. Opening
hours are read when they are in a common format. Otherwise the stop says "Hours unconfirmed".
Late-night food is only suggested when hours confirm it is open.

Being kind to free services: map queries are snapped to a grid and cached for a week, counted
against a daily budget shared by all visitors (`DW_OVERPASS_DAILY_LIMIT`, default 80), sent with a
User-Agent, retried on a backup server, and served from older cache if every server is down.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py                  # http://127.0.0.1:5000
python -m pytest -q            # tests, no internet needed
```

Optional environment variables:

- `TICKETMASTER_KEY` turns on the "Also on tonight" list (free key at developer.ticketmaster.com).
- `DW_CONTACT` is the URL put in the User-Agent. Set it to your own repo or site.
- `DW_OVERPASS_DAILY_LIMIT` caps live map queries per day.

## Deploy free on Render

Easiest: in Render, New, then **Blueprint**, and pick this repo. `render.yaml` sets up a free web
service with a health check on `/healthz`.

By hand instead: New, then **Web Service**, pick this repo, and use

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Instance type: Free. It sleeps when idle and takes about a minute to wake.

`gunicorn.conf.py` is picked up automatically. It runs one worker with eight threads (the rate
limits and caches live in memory, so they need one process) and a 120 second timeout, because a
plan can wait on the main map server and then the backup. Python is pinned in `.python-version`.

The deal board and map cache live on local disk. On free hosting that disk resets when the app
restarts, so deals and cache can disappear. Fine for a demo. For real use, point `DW_DATA_DIR` at a
persistent disk or swap the JSON file for a small database.

### When the free sources say no

- **Overpass** servers get busy, and some refuse cloud IP ranges. A server that fails is rested for
  three minutes so visitors get a quick answer instead of a long wait, and an answer with a
  "runtime error" remark is treated as a failure, never cached as an empty neighborhood.
- **Open-Meteo** has a daily limit per IP, and free hosts share IPs. Forecasts are cached for three
  hours, and when the forecast can't be reached the plan says so instead of leaving it out quietly.

## Tests

Tests cover the hours parser, price estimates, duplicate merging, the planner (never picks a
pricey place, only open places, honest when the map has no live music), the budget meter, every
export, input checks, rate limiting, and each outside source being down. A voice test fails the
build if any line in the app uses stiff phrases or dashes. Test data in `tests/fixtures` is
synthetic. `tests/ui_harness.py` runs the app on that data to look at the screens offline.

## Credits and limits

Map data is from OpenStreetMap contributors (ODbL). Weather by Open-Meteo. Not affiliated with any
bar. Prices and hours can be wrong, so call ahead. Drink responsibly, and do not drive.

MIT license.
