"""Truck routes from Valhalla (FOSSGIS public server, no key)."""

import math
from collections import Counter
from collections.abc import Iterator

import httpx
import polyline
from django.conf import settings

from trips.engine.geo import (
    MI_PER_DEG_LAT,
    LonLat,
    cumulative_miles,
    haversine_mi,
    offset_mi,
    point_at,
)
from trips.engine.route import RouteGeometry
from trips.errors import NoRouteError, ProviderError

from .http import client_or_new

LB_TO_TONNES = 0.000453592
MAX_DETOUR_RATIO = 1.6  # a detour may take at most 60% longer than the fastest route
MAX_OVERLAP = 0.8  # share of a candidate already covered by existing routes
DETOUR_FRACTIONS = (0.15, -0.15, 0.30, -0.30)  # sideways offset as a share of trip length
OVERLAP_CELL_DEG = 0.01  # ~0.7 mi
MAX_DISTANCE_ERROR = 154  # Valhalla: path distance exceeds the server limit


def fetch_routes(
    origin: LonLat,
    destination: LonLat,
    load_lb: float,
    *,
    want: int = 3,
    client: httpx.Client | None = None,
) -> list[RouteGeometry]:
    with client_or_new(client) as http:
        data = _post(http, _body([origin, destination], load_lb, alternates=want - 1))
        routes: list[RouteGeometry] = []
        for trip in [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]:
            candidate = parse_trip(trip)
            if not routes or overlap(candidate, routes) <= MAX_OVERLAP:
                routes.append(candidate)

        for via in detour_points(origin, destination):
            if len(routes) >= want:
                break
            try:
                candidate = parse_trip(_via_trip(http, origin, via, destination, load_lb))
            except NoRouteError:
                continue
            fastest = min(r.duration_s for r in routes)
            if (
                candidate.duration_s <= MAX_DETOUR_RATIO * fastest
                and overlap(candidate, routes) <= MAX_OVERLAP
            ):
                routes.append(candidate)
    return routes[:want]


def _via_trip(
    http: httpx.Client, origin: LonLat, via: LonLat, destination: LonLat, load_lb: float
) -> dict:
    """A route forced through `via`, requested as two legs and joined.

    The public server caps multi-location requests at 1,500 km of straight-line
    distance, which a detour across a long trip exceeds; two single-leg requests don't.
    """
    first = _post(http, _body([origin, via], load_lb, alternates=0))["trip"]
    second = _post(http, _body([via, destination], load_lb, alternates=0))["trip"]
    return {
        "legs": first["legs"] + second["legs"],
        "summary": {k: first["summary"][k] + second["summary"][k] for k in ("length", "time")},
    }


def _body(points: list[LonLat], load_lb: float, *, alternates: int) -> dict:
    return {
        "locations": [{"lat": lat, "lon": lon} for lon, lat in points],
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(load_lb * LB_TO_TONNES, 2)}},
        "units": "miles",
        "alternates": alternates,
        "directions_options": {"units": "miles"},
    }


def _post(http: httpx.Client, body: dict) -> dict:
    try:
        response = http.post(settings.VALHALLA_URL, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError("The routing service didn't respond. Try again in a minute.") from exc
    if response.status_code == 400 and _error_code(response) == MAX_DISTANCE_ERROR:
        raise NoRouteError(
            "This trip is longer than the free routing service allows (about 930 miles in a "
            "straight line). Pick a closer destination or split the trip."
        )
    if response.status_code == 400:
        raise NoRouteError(
            "No truck route connects these places. Pick a start and destination reachable by road."
        )
    if response.status_code != 200:
        raise ProviderError("The routing service is having trouble. Try again in a minute.")
    return response.json()


def _error_code(response: httpx.Response) -> int | None:
    try:
        return response.json().get("error_code")
    except ValueError:
        return None


def parse_trip(trip: dict) -> RouteGeometry:
    points: list[LonLat] = []
    seconds: list[float] = []
    names: Counter[str] = Counter()
    for leg in trip["legs"]:
        shape = [(lon, lat) for lat, lon in polyline.decode(leg["shape"], 6)]
        cum = cumulative_miles(shape)
        leg_seconds = [0.0] * len(shape)
        for m in leg["maneuvers"]:
            begin, end = m["begin_shape_index"], m["end_shape_index"]
            span = cum[end] - cum[begin]
            for k in range(begin + 1, end + 1):
                share = (cum[k] - cum[k - 1]) / span if span > 0 else 1 / (end - begin)
                leg_seconds[k] = leg_seconds[k - 1] + m["time"] * share
            for name in m.get("street_names", []):
                names[name] += m["length"]
        if points:  # each leg starts where the previous ended
            shape, leg_seconds = shape[1:], leg_seconds[1:]
        start = seconds[-1] if seconds else 0.0
        points += shape
        seconds += [start + s for s in leg_seconds]

    cum_miles = cumulative_miles(points)
    summary = trip["summary"]
    mile_scale = summary["length"] / cum_miles[-1] if cum_miles[-1] > 0 else 1.0
    time_scale = summary["time"] / seconds[-1] if seconds[-1] > 0 else 1.0
    return RouteGeometry(
        label=" · ".join(name for name, _ in names.most_common(2)) or "Local roads",
        points=points,
        cum_miles=[m * mile_scale for m in cum_miles],
        cum_seconds=[s * time_scale for s in seconds],
    )


def detour_points(origin: LonLat, destination: LonLat) -> Iterator[LonLat]:
    """Via points on either side of the straight line, near its middle."""
    mid = ((origin[0] + destination[0]) / 2, (origin[1] + destination[1]) / 2)
    east = (destination[0] - origin[0]) * MI_PER_DEG_LAT * math.cos(math.radians(mid[1]))
    north = (destination[1] - origin[1]) * MI_PER_DEG_LAT
    norm = math.hypot(east, north) or 1.0
    side_east, side_north = -north / norm, east / norm
    trip_mi = haversine_mi(origin, destination)
    for fraction in DETOUR_FRACTIONS:
        distance = math.copysign(min(max(abs(fraction) * trip_mi, 10.0), 150.0), fraction)
        yield offset_mi(mid, side_east * distance, side_north * distance)


def _samples(route: RouteGeometry, step_mi: float) -> list[LonLat]:
    count = int(route.distance_mi / step_mi) + 1
    return [point_at(route.points, route.cum_miles, k * step_mi) for k in range(count)]


def _cell(p: LonLat) -> tuple[int, int]:
    return (round(p[1] / OVERLAP_CELL_DEG), round(p[0] / OVERLAP_CELL_DEG))


def overlap(candidate: RouteGeometry, existing: list[RouteGeometry]) -> float:
    covered: set[tuple[int, int]] = set()
    for route in existing:
        for p in _samples(route, 0.5):
            r, c = _cell(p)
            covered.update((r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1))
    samples = _samples(candidate, 2.0)
    return sum(_cell(p) in covered for p in samples) / len(samples)
