"""One shared HTTP session, a polite User-Agent, and small helpers."""
import json
import os
import threading
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .. import config

session = requests.Session()
session.headers.update({"User-Agent": config.USER_AGENT})
# Free APIs drop connections now and then. Retry a GET that never got an answer, or got a 502-504,
# a couple of times with a short pause. Never retry 429 and never obey Retry-After: a rate-limited
# source can say "tomorrow", and waiting on that would freeze the whole plan request.
# and never retry the Overpass POST here: it has its own backup server.
_retry = Retry(total=2, connect=2, read=1, status=2, backoff_factor=0.8,
               status_forcelist=(502, 503, 504), allowed_methods=frozenset({"GET"}), respect_retry_after_header=False)
session.mount("https://", HTTPAdapter(max_retries=_retry))

_locks: dict[str, threading.Lock] = {}
_last: dict[str, float] = {}


def throttle(name: str, min_interval: float) -> None:
    """Wait so that calls under one name are at least min_interval seconds apart."""
    lock = _locks.setdefault(name, threading.Lock())
    with lock:
        wait = _last.get(name, 0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[name] = time.monotonic()


def _quota_file():
    return config.DATA_DIR / "quota.json"


_quota_lock = threading.Lock()


def take_quota(name: str, limit: int) -> bool:
    """Count a call against a daily budget shared by every visitor. False if used up."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _quota_lock:
        try:
            data = json.loads(_quota_file().read_text())
        except (OSError, ValueError):
            data = {}
        if data.get("day") != today:
            data = {"day": today}
        used = int(data.get(name, 0))
        if used >= limit:
            return False
        data[name] = used + 1
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _quota_file().with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            os.replace(tmp, _quota_file())
        except OSError:
            pass
        return True
