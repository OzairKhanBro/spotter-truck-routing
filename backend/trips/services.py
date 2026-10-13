"""Turns a trip request into scored routes. Orchestration only; rules live in engine/."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from django.utils import timezone

from .engine.checkpoints import CheckpointPosition, place_checkpoints, slice_path, thin
from .engine.corridor import build_grid, corridor_scores
from .engine.forecast import Conditions, conditions_at
from .engine.geo import LonLat, haversine_mi
from .engine.risk import Assessment, assess
from .engine.route import RouteGeometry
from .engine.scoring import Candidate, RouteSummary, recommend, segment_levels, summarize
from .errors import TripError
from .models import Trip
from .providers.open_meteo import fetch_series
from .providers.valhalla import fetch_routes

ROUTE_IDS = "ABC"
DEPARTURE_GRACE = timedelta(hours=1)
MAX_DEPARTURE_AHEAD = timedelta(days=7)


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    @property
    def point(self) -> LonLat:
        return (self.lon, self.lat)


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime
    load_lb: int
    interval_mi: int


@dataclass(frozen=True)
class _Row:
    position: CheckpointPosition
    eta: datetime
    conditions: Conditions
    assessment: Assessment


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _coords(points: list[LonLat]) -> list[list[float]]:
    return [[round(lon, 5), round(lat, 5)] for lon, lat in points]


def _validate(req: TripRequest, now: datetime) -> None:
    if req.departure < now - DEPARTURE_GRACE:
        raise TripError("Departure is in the past. Pick a time from now on.")
    if req.departure > now + MAX_DEPARTURE_AHEAD:
        raise TripError(
            "Forecasts reach about a week out. Pick a departure within the next 7 days."
        )
    if haversine_mi(req.origin.point, req.destination.point) < 1:
        raise TripError("Start and destination are the same place. Pick a different destination.")


def plan_trip(req: TripRequest, *, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    _validate(req, now)
    departure = req.departure.astimezone(UTC)

    routes = fetch_routes(req.origin.point, req.destination.point, req.load_lb)
    placed = [place_checkpoints(route, req.interval_mi) for route in routes]
    series = iter(fetch_series([(c.lon, c.lat) for cps in placed for c in cps]))

    out_routes, candidates = [], []
    for route_id, route, positions in zip(ROUTE_IDS, routes, placed):
        rows = []
        for position in positions:
            eta = departure + timedelta(seconds=position.offset_s)
            conditions = conditions_at(next(series), eta)
            if conditions is None:
                raise TripError(
                    f"Route {route_id} reaches mile {position.mile:.0f} at "
                    f"{eta:%a %H:%M} UTC, beyond the forecast. Pick an earlier departure."
                )
            assessment = assess(
                wind_mph=conditions.wind_mph,
                rain_in_hr=conditions.rain_in_hr,
                snow_in_hr=conditions.snow_in_hr,
                load_lb=req.load_lb,
            )
            rows.append(_Row(position, eta, conditions, assessment))
        summary = summarize([r.position.mile for r in rows], [r.assessment.level for r in rows])
        candidates.append(Candidate(route_id, summary, route.duration_s))
        out_routes.append(_route_json(route_id, route, rows, summary))

    recommendation = recommend(candidates)
    for r in out_routes:
        r["rank"] = recommendation.ranking.index(r["id"]) + 1
    notes = []
    if len(routes) < len(ROUTE_IDS):
        notes.append(f"Only {len(routes)} distinct truck routes exist between these places.")

    return {
        "origin": vars(req.origin),
        "destination": vars(req.destination),
        "departure": _iso(departure),
        "load_lb": req.load_lb,
        "interval_mi": req.interval_mi,
        "timeline_start": _iso(floor_hour(departure)),
        "routes": out_routes,
        "recommendation": {
            "route_id": recommendation.route_id,
            "reason": recommendation.reason,
            "all_blocked": recommendation.all_blocked,
        },
        "notes": notes,
    }


def _route_json(
    route_id: str, route: RouteGeometry, rows: list[_Row], summary: RouteSummary
) -> dict:
    path = thin(route)
    miles = [r.position.mile for r in rows]
    levels = [r.assessment.level for r in rows]
    return {
        "id": route_id,
        "label": route.label,
        "distance_mi": round(route.distance_mi, 2),
        "duration_s": round(route.duration_s),
        "arrival": _iso(rows[-1].eta),
        "path": {
            "coordinates": _coords(path.points),
            "seconds": [round(s) for s in path.cum_seconds],
        },
        "segments": [
            {
                "level": level.slug,
                "start_mile": start,
                "end_mile": end,
                "coordinates": _coords(slice_path(path, start, end)),
            }
            for (start, end), level in zip(pairwise(miles), segment_levels(levels))
        ],
        "checkpoints": [
            {
                "mile": r.position.mile,
                "lon": round(r.position.lon, 5),
                "lat": round(r.position.lat, 5),
                "eta": _iso(r.eta),
                "wind_mph": r.conditions.wind_mph,
                "gust_mph": r.conditions.gust_mph,
                "rain_in_hr": round(r.conditions.rain_in_hr, 3),
                "snow_in_hr": round(r.conditions.snow_in_hr, 3),
                "level": r.assessment.level.slug,
                "drivers": list(r.assessment.drivers),
                "load_adjusted": r.assessment.load_adjusted,
            }
            for r in rows
        ],
        "summary": {
            "miles_by_level": {lvl.slug: m for lvl, m in summary.miles_by_level.items()},
            "avg_risk": summary.avg_risk,
            "max_level": summary.max_level.slug,
        },
    }


def build_corridor(trip: Trip) -> dict:
    if trip.corridor:
        return trip.corridor
    paths = [[tuple(p) for p in r["path"]["coordinates"]] for r in trip.result["routes"]]
    grid = build_grid(paths)
    start = datetime.fromisoformat(trip.result["timeline_start"])
    frames = corridor_scores(grid, fetch_series(grid.centers), start, trip.load_lb)
    trip.corridor = {
        "start": trip.result["timeline_start"],
        "bounds": [round(v, 5) for v in (grid.west, grid.south, grid.east, grid.north)],
        "cols": grid.cols,
        "rows": grid.rows,
        "scores": frames,
    }
    trip.save(update_fields=["corridor"])
    return trip.corridor
