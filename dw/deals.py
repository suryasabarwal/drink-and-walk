"""A small community board for deals the map can't know: "$3 pints Tuesday".

Stored in a JSON file. On free hosting that file can reset when the app restarts, and the
README says so. Entries are short plain text, rate limited, and hidden after 180 days or
after two "this is gone" reports.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from typing import Any

from . import config

MAX_DEALS = 2000
EXPIRE_DAYS = 180
_lock = threading.Lock()
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_LINKY = re.compile(r"https?:|www\.|\.com|\.net|\.org|@", re.I)


class DealError(ValueError):
    pass


def _path():
    return config.DATA_DIR / "deals.json"


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return []


def _save(deals: list[dict[str, Any]]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    tmp.write_text(json.dumps(deals))
    os.replace(tmp, _path())


def clean(text: Any, lo: int, hi: int, field: str) -> str:
    s = _CTRL.sub(" ", str(text or "")).strip()
    s = re.sub(r"\s+", " ", s)
    if not (lo <= len(s) <= hi):
        raise DealError(f"{field} needs {lo} to {hi} characters")
    if _LINKY.search(s):
        raise DealError("Leave links and email addresses out. Just describe the deal.")
    return s


def add(place_id: str, place_name: str, text: str, when: str) -> dict[str, Any]:
    if not re.fullmatch(r"[nwr]\d{1,12}", str(place_id or "")):
        raise DealError("pick a place from the plan first")
    deal = {
        "id": secrets.token_hex(5),
        "place_id": place_id,
        "place_name": clean(place_name, 1, 80, "place name"),
        "text": clean(text, 8, 140, "deal"),
        "when": clean(when, 0, 40, "when") if (when or "").strip() else "",
        "added": int(time.time()),
        "gone": 0,
    }
    with _lock:
        deals = _load()
        deals.append(deal)
        _save(deals[-MAX_DEALS:])
    return deal


def _live(d: dict[str, Any]) -> bool:
    return d.get("gone", 0) < 2 and time.time() - d.get("added", 0) < EXPIRE_DAYS * 86400


def for_places(place_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in _load():
        if d["place_id"] in place_ids and _live(d):
            out.setdefault(d["place_id"], []).append(
                {"id": d["id"], "text": d["text"], "when": d.get("when", ""), "days_old": int((time.time() - d["added"]) // 86400)}
            )
    return out


def report_gone(deal_id: str) -> bool:
    with _lock:
        deals = _load()
        for d in deals:
            if d["id"] == deal_id:
                d["gone"] = d.get("gone", 0) + 1
                _save(deals)
                return True
    return False
