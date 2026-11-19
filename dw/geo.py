"""Distance and walking time."""
from math import asin, cos, radians, sin, sqrt

from . import config


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dl = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def walk_minutes(meters: float) -> int:
    """Rough street walking time. Straight-line distance times a detour factor."""
    if meters <= 0:
        return 0
    return max(1, round(meters * config.DETOUR_FACTOR / config.WALK_M_PER_MIN))


def walk_km_label(meters: float) -> str:
    miles = meters * config.DETOUR_FACTOR / 1609.34
    return f"{miles:.1f} mi" if miles >= 0.1 else "a few steps"
