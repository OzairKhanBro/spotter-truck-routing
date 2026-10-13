from datetime import UTC, datetime, timedelta

from trips.engine.forecast import HourlySeries
from trips.engine.geo import LonLat, cumulative_miles
from trips.engine.route import RouteGeometry


def straight_route(
    label: str, start: LonLat, end: LonLat, hours: float, n: int = 21
) -> RouteGeometry:
    """Evenly spaced straight route driven at constant speed."""
    points = [
        (start[0] + (end[0] - start[0]) * i / (n - 1), start[1] + (end[1] - start[1]) * i / (n - 1))
        for i in range(n)
    ]
    cum = cumulative_miles(points)
    seconds = [hours * 3600 * m / cum[-1] for m in cum]
    return RouteGeometry(label=label, points=points, cum_miles=cum, cum_seconds=seconds)


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def flat_series(
    start: datetime, hours: int = 240, wind: float = 5.0, rain: float = 0.0, snow: float = 0.0
) -> HourlySeries:
    times = [start + timedelta(hours=h) for h in range(hours)]
    return HourlySeries(
        times=times,
        wind_mph=[wind] * hours,
        gust_mph=[wind * 1.4] * hours,
        rain_in=[rain] * hours,
        snow_in=[snow] * hours,
    )
