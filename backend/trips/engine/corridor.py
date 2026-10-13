"""A coarse lon/lat grid around the routes, scored hour by hour for the heatmap."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .forecast import HourlySeries, conditions_at
from .geo import MI_PER_DEG_LAT, LonLat
from .risk import assess

MAX_CELLS = 2500
MAX_ACTIVE = 250  # each active cell is one Open-Meteo location
GROWTH = 1.25
MASKED = -1.0


@dataclass(frozen=True)
class Grid:
    west: float
    south: float
    east: float
    north: float
    cols: int
    rows: int
    active: list[int]  # row * cols + col, row 0 is the north edge
    centers: list[LonLat]  # one per active index


def build_grid(
    paths: list[list[LonLat]], *, cell_mi: float = 20.0, buffer_mi: float = 40.0
) -> Grid:
    points = [p for path in paths for p in path]
    while True:
        grid = _grid(points, cell_mi, buffer_mi)
        if grid.cols * grid.rows <= MAX_CELLS and len(grid.active) <= MAX_ACTIVE:
            return grid
        cell_mi *= GROWTH


def _grid(points: list[LonLat], cell_mi: float, buffer_mi: float) -> Grid:
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    mi_per_deg_lon = MI_PER_DEG_LAT * math.cos(math.radians((min(lats) + max(lats)) / 2))
    dlat, dlon = cell_mi / MI_PER_DEG_LAT, cell_mi / mi_per_deg_lon
    west = min(lons) - buffer_mi / mi_per_deg_lon
    north = max(lats) + buffer_mi / MI_PER_DEG_LAT
    cols = max(1, math.ceil((max(lons) + buffer_mi / mi_per_deg_lon - west) / dlon))
    rows = max(1, math.ceil((north - (min(lats) - buffer_mi / MI_PER_DEG_LAT)) / dlat))

    reach = math.ceil(buffer_mi / cell_mi)
    touched = {(int((north - lat) / dlat), int((lon - west) / dlon)) for lon, lat in points}
    active: set[int] = set()
    for r, c in touched:
        for dr in range(-reach, reach + 1):
            for dc in range(-reach, reach + 1):
                rr, cc = r + dr, c + dc
                if dr * dr + dc * dc <= reach * reach and 0 <= rr < rows and 0 <= cc < cols:
                    active.add(rr * cols + cc)
    ordered = sorted(active)
    return Grid(
        west=west,
        south=north - rows * dlat,
        east=west + cols * dlon,
        north=north,
        cols=cols,
        rows=rows,
        active=ordered,
        centers=[
            (west + (i % cols + 0.5) * dlon, north - (i // cols + 0.5) * dlat) for i in ordered
        ],
    )


def corridor_scores(
    grid: Grid, series: list[HourlySeries], start: datetime, load_lb: float, hours: int = 48
) -> list[list[float]]:
    frames = []
    for h in range(hours + 1):
        when = start + timedelta(hours=h)
        frame = [MASKED] * (grid.cols * grid.rows)
        for index, s in zip(grid.active, series):
            c = conditions_at(s, when)
            if c is not None:
                frame[index] = assess(
                    wind_mph=c.wind_mph,
                    rain_in_hr=c.rain_in_hr,
                    snow_in_hr=c.snow_in_hr,
                    load_lb=load_lb,
                ).score
        frames.append(frame)
    return frames
