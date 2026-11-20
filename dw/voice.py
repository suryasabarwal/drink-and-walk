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
        "Eat now. The beer will still be there, judging you.",
    ],
    "happy": [
        "The cheap hour. Ask what's on special before anyone orders.",
        "Happy hour, if they still run one. Asking takes five seconds.",
        "Start drinking here while the prices are still friendly.",
        "Cheapest drinks of the night, in theory. Check the board by the door.",
        "Early drinks, smaller tab. Future you approves.",
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
        "Low lights, lower prices. You are among friends.",
    ],
    "lively": [
        "The loud one. Go in with a plan: one round, then check in with each other.",
        "Busy place, so grab a spot early and order together.",
        "Good spot to get a little louder. Keep an eye on the tab.",
        "Turn it up a notch. Not the tab, just the night.",
    ],
    "breather": [
        "Sit down for a bit. Water, a snack, maybe a coffee. This is called pacing.",
        "Quiet corner, cheap refill. Let the legs recover.",
        "Slow lap. Order water with the next round and nobody will notice.",
        "Halftime. Water, a seat, and a decision about round three.",
    ],
    "last": [
        "One more, then call it. The ride home is sorted, right?",
        "Last stop. Close out your tab before the group dissolves.",
        "Final round. Split the check before anyone leaves, not after.",
        "One more, then bed. Somebody has a meeting in somebody else's morning.",
    ],
    "late": [
        "Late bite. A slice on the walk back has saved a lot of nights.",
        "Last food stop. Eat it on the way home, no judgement.",
        "Hungry again at midnight. Right on schedule.",
        "Something greasy for the walk home. Tradition.",
    ],
    # one line per place in "I'm out right now", by what you asked for
    "near_drink": [
        "Close enough that leaving early is still an option.",
        "Short walk, short tab. Tonight asks for very little.",
        "One drink here, then decide. Nobody has to know there was a plan.",
        "Good for one. Possibly two. We are not your accountant.",
    ],
    "near_eat": [
        "Real food, fair price. Your stomach filed a complaint an hour ago.",
        "Eat something that is not a bar snack. Small victories.",
        "Cheap, filling and open. That is the whole review.",
    ],
    "near_music": [
        "Someone is playing something. Tip the band.",
        "Live music, if the map is honest. Check the door for a cover.",
        "Loud enough to skip the small talk. Efficient.",
    ],
    "near_free": [
        "Cheap or free to walk into. Your wallet can stay in your pocket.",
        "Low cost of entry, decent odds of a story.",
        "The best price is the one nobody charges you.",
    ],
    "near_late": [
        "Open late, confirmed. Midnight you will be grateful.",
        "Salt, grease and a closing time later than yours.",
        "The last good decision of the night.",
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
    "tagline": "Cheap bars and food that are open now, a short walk away.",
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
