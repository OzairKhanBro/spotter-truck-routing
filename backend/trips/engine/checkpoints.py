"""Where along a route we sample weather, and when the truck gets there."""

import math
from dataclasses import dataclass

from .geo import LonLat, point_at, sample
from .route import RouteGeometry


@dataclass(frozen=True)
class CheckpointPosition:
    mile: float
    lon: float
    lat: float
    offset_s: float  # drive time from departure


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """Origin, every `interval_mi`, and the destination."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    count = math.ceil(total_mi / interval_mi)
    return [k * interval_mi for k in range(count)] + [total_mi]


def place_checkpoints(route: RouteGeometry, interval_mi: float) -> list[CheckpointPosition]:
    out = []
    for mile in checkpoint_miles(route.distance_mi, interval_mi):
        lon, lat = point_at(route.points, route.cum_miles, mile)
        offset = sample(route.cum_miles, route.cum_seconds, mile)
        out.append(CheckpointPosition(mile=round(mile, 2), lon=lon, lat=lat, offset_s=offset))
    return out


def thin(route: RouteGeometry, step_mi: float = 0.5) -> RouteGeometry:
    """Drop vertices closer than step_mi to the previous kept one; keep both ends."""
    keep = [0]
    for k in range(1, len(route.points) - 1):
        if route.cum_miles[k] - route.cum_miles[keep[-1]] >= step_mi:
            keep.append(k)
    if len(route.points) > 1:
        keep.append(len(route.points) - 1)
    return RouteGeometry(
        label=route.label,
        points=[route.points[k] for k in keep],
        cum_miles=[route.cum_miles[k] for k in keep],
        cum_seconds=[route.cum_seconds[k] for k in keep],
    )


def slice_path(route: RouteGeometry, start_mi: float, end_mi: float) -> list[LonLat]:
    inner = [p for p, m in zip(route.points, route.cum_miles) if start_mi < m < end_mi]
    return [
        point_at(route.points, route.cum_miles, start_mi),
        *inner,
        point_at(route.points, route.cum_miles, end_mi),
    ]
