"""A small parser for the common shapes of OpenStreetMap opening_hours.

It handles things like "Mo-Fr 16:00-02:00; Sa,Su 12:00-00:00" and "24/7".
Anything fancier (sunrise, week numbers, "PH" rules) is treated as unknown, and the app says
"hours unconfirmed" instead of guessing.

Days are 0=Monday ... 6=Sunday. Minutes are counted from midnight of that day and may go past
1440 to mean "after midnight, still that night".
"""
from __future__ import annotations

import re

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_TIME = r"(\d{1,2}):(\d{2})"
_RANGE = re.compile(rf"^{_TIME}\s*-\s*{_TIME}$")


class Hours:
    def __init__(self, week: list[list[tuple[int, int]]] | None):
        self.week = week  # None means unknown

    @property
    def known(self) -> bool:
        return self.week is not None

    def is_open(self, day: int, minute: int) -> bool | None:
        """True/False if we know, None if the hours could not be read."""
        if self.week is None:
            return None
        d = day % 7
        m = minute
        while m >= 1440:
            d = (d + 1) % 7
            m -= 1440
        for start, end in self.week[d]:
            if start <= m < end:
                return True
        # Hours from the day before that run past midnight.
        for start, end in self.week[(d - 1) % 7]:
            if end > 1440 and m + 1440 < end:
                return True
        # And the original day, in case the caller used the previous day's carryover form.
        return False


def _expand_days(spec: str) -> list[int] | None:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (x.strip()[:2].title() for x in part.split("-", 1))
            if a not in DAYS or b not in DAYS:
                return None
            i, j = DAYS.index(a), DAYS.index(b)
            span = range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
            out.extend(span)
        else:
            p = part[:2].title()
            if p not in DAYS:
                return None
            out.append(DAYS.index(p))
    return out or None


def _times(spec: str) -> list[tuple[int, int]] | None:
    spans: list[tuple[int, int]] = []
    for chunk in spec.split(","):
        m = _RANGE.match(chunk.strip())
        if not m:
            return None
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
            return None
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 1440  # crosses midnight (also covers 00:00 as a closing time)
        spans.append((start, end))
    return spans or None


def parse(text: str | None) -> Hours:
    if not text or not text.strip():
        return Hours(None)
    raw = text.strip()
    if raw == "24/7":
        return Hours([[(0, 1440)] for _ in range(7)])
    week: list[list[tuple[int, int]]] = [[] for _ in range(7)]
    for rule in raw.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        if re.search(r"\bPH\b|sunrise|sunset|week|dawn|dusk|\[|\"|easter", rule, re.I):
            # Public-holiday and sun-based rules: skip pure PH rules, give up on the rest.
            if re.fullmatch(r"PH\s+(off|closed)", rule, re.I):
                continue
            return Hours(None)
        m = re.match(r"^([A-Za-z,\- ]+?)\s+(off|closed)$", rule, re.I)
        if m:
            days = _expand_days(m.group(1))
            if days is None:
                return Hours(None)
            for d in days:
                week[d] = []
            continue
        m = re.match(r"^([A-Za-z,\-]+)\s+(\d.*)$", rule)
        if m:
            days = _expand_days(m.group(1))
            times = _times(m.group(2))
        elif re.match(r"^\d", rule):
            days = list(range(7))
            times = _times(rule)
        else:
            return Hours(None)
        if days is None or times is None:
            return Hours(None)
        for d in days:
            week[d] = list(times)
    return Hours(week)
