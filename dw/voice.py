"""All the lines the app says. Written by hand on purpose: short, dry, no hype.

tests/test_voice.py fails if any line here (or in the page) uses stiff phrases or dashes.
"""
from __future__ import annotations

import zlib

LINES = {
    "eat": [
        "Food first. Cheap beer on an empty stomach is a rookie move.",
        "Line your stomachs. Nobody wants to be the friend who needs a bench by nine.",
        "Real food now, so the drinks later hit slower and cost the same.",
        "Dinner is the one place not to be stingy. Get something filling.",
    ],
    "happy": [
        "The cheap hour. Ask what's on special before anyone orders.",
        "Happy hour, if they still run one. Asking takes five seconds.",
        "Start drinking here while the prices are still friendly.",
        "Cheapest drinks of the night, in theory. Check the board by the door.",
    ],
    "music": [
        "Live music, and nobody should be charging fifteen bucks for a beer. Check the door for a cover.",
        "Sit near the band, tip a few bucks, keep your own tab small.",
        "Music tonight. Look for a cover charge before you commit to a table.",
    ],
    "dive": [
        "Proper dive energy. Bring cash, and split a pitcher.",
        "Sticky floor, fair prices. This is the main event.",
        "A pitcher splits better than six single beers. Group math wins.",
    ],
    "lively": [
        "The loud one. Go in with a plan: one round, then check in with each other.",
        "Busy place, so grab a spot early and order together.",
        "Good spot to get a little louder. Keep an eye on the tab.",
    ],
    "breather": [
        "Sit down for a bit. Water, a snack, maybe a coffee. This is called pacing.",
        "Quiet corner, cheap refill. Let the legs recover.",
        "Slow lap. Order water with the next round and nobody will notice.",
    ],
    "last": [
        "One more, then call it. The ride home is sorted, right?",
        "Last stop. Close out your tab before the group dissolves.",
        "Final round. Split the check before anyone leaves, not after.",
    ],
    "late": [
        "Late bite. A slice on the walk back has saved a lot of nights.",
        "Last food stop. Eat it on the way home, no judgement.",
        "Hungry again at midnight. Right on schedule.",
    ],
}

SLOT_LABELS = {
    "eat": "Eat first",
    "happy": "Happy hour",
    "music": "Live music",
    "dive": "Main stop",
    "lively": "Main stop",
    "breather": "Breather",
    "last": "Last one",
    "late": "Late bite",
}

UI = {
    "tagline": "A cheap night out for friends splitting the bill.",
    "sub": "Pick a city and where you're starting. We build a walking route of cheap food, happy hours and live music.",
    "safety_title": "Before you head out",
    "safety": [
        "Eat before the first drink and have water between rounds.",
        "Pick the ride home now, before anyone has had a drink. Don't drive.",
        "Stay together and stay on the route. Nobody walks home alone.",
        "In the US you need to be 21 for the bar stops.",
    ],
    "estimate_note": "Prices are estimates from the type of place. Call or check the menu before you go.",
    "thin": "The map only knows a few places here. Try searching wider or start from a busier spot.",
    "no_live": "No live music found on the map near this route. Search the venue's page or Reddit for tonight's lineup.",
    "no_late": "No late-night food with listed hours near this route. Call a pizza place and ask when they close.",
    "hours_unknown": "Hours unconfirmed",
    "open_then": "Open then",
    "closed_then": "Closed then",
}


def pick(group: str, seed: str) -> str:
    bank = LINES[group]
    return bank[zlib.crc32(seed.encode()) % len(bank)]


def all_text() -> list[str]:
    out = [s for bank in LINES.values() for s in bank]
    out += list(SLOT_LABELS.values())
    for v in UI.values():
        out += v if isinstance(v, list) else [v]
    return out
