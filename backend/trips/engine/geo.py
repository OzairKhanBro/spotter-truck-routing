"""Small spherical-geometry helpers. Coordinates are (lon, lat) tuples."""

import math
from bisect import bisect_right
from itertools import pairwise

LonLat = tuple[float, float]

EARTH_RADIUS_MI = 3958.7613
MI_PER_DEG_LAT = 69.0


def haversine_mi(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(points: list[LonLat]) -> list[float]:
    out = [0.0]
    for a, b in pairwise(points):
        out.append(out[-1] + haversine_mi(a, b))
    return out


def locate(cum: list[float], at: float) -> tuple[int, float]:
    """Segment index i and fraction f so that `at` lies f of the way from cum[i] to cum[i+1]."""
    if len(cum) == 1 or at <= cum[0]:
        return 0, 0.0
    if at >= cum[-1]:
        return len(cum) - 2, 1.0
    i = bisect_right(cum, at) - 1
    span = cum[i + 1] - cum[i]
    return i, (at - cum[i]) / span if span > 0 else 0.0


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def sample(cum: list[float], values: list[float], at: float) -> float:
    if len(cum) == 1:
        return values[0]
    i, f = locate(cum, at)
    return _lerp(values[i], values[i + 1], f)


def point_at(points: list[LonLat], cum: list[float], at: float) -> LonLat:
    if len(points) == 1:
        return points[0]
    i, f = locate(cum, at)
    (lon1, lat1), (lon2, lat2) = points[i], points[i + 1]
    return (_lerp(lon1, lon2, f), _lerp(lat1, lat2, f))


def offset_mi(p: LonLat, east_mi: float, north_mi: float) -> LonLat:
    lon, lat = p
    return (
        lon + east_mi / (MI_PER_DEG_LAT * math.cos(math.radians(lat))),
        lat + north_mi / MI_PER_DEG_LAT,
    )
