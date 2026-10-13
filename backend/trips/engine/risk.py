"""Weather risk rules from the brief. Pure functions, no I/O."""

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def slug(self) -> str:
        return self.name.lower()


# Lower edge of Moderate, High, Severe, No Travel. A value on an edge belongs to the higher band.
WIND_EDGES_MPH = (25.0, 35.0, 45.0, 55.0)  # No Travel is ">= 55"
RAIN_EDGES_IN_HR = (0.10, 0.25, 0.50, 1.00)  # No Travel is "> 1.00"
SNOW_EDGES_IN_HR = (0.5, 1.0, 2.0, 3.0)  # No Travel is "> 3.0"

HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # with Severe wind
HEAVY_LOAD_SEVERE_LB = 40_000  # with High wind

_MAX_FRACTION = 0.99  # keeps floor(score) == level


@dataclass(frozen=True)
class Assessment:
    level: Level
    drivers: tuple[str, ...]
    load_adjusted: bool
    score: float  # level + progress through that band, 0..4, for the heatmap


def _band(value: float, edges: tuple[float, ...], *, top_inclusive: bool) -> tuple[Level, float]:
    """Return the band for value and how far (0..0.99) it sits inside that band."""
    value = max(value, 0.0)
    top = edges[-1]
    if value > top or (top_inclusive and value >= top):
        return Level.NO_TRAVEL, 0.0
    bounds = (0.0, *edges)
    for lvl in (Level.SEVERE, Level.HIGH, Level.MODERATE, Level.LOW):
        lo, hi = bounds[lvl], bounds[lvl + 1]
        if value >= lo:
            return lvl, min((value - lo) / (hi - lo), _MAX_FRACTION)
    raise AssertionError("unreachable: value >= 0")


def _apply_load_rules(wind: Level, load_lb: float) -> Level:
    if wind == Level.SEVERE and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return Level.NO_TRAVEL
    if wind == Level.HIGH and load_lb > HEAVY_LOAD_SEVERE_LB:
        return Level.SEVERE
    return wind


def assess(*, wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    wind_base, wind_frac = _band(wind_mph, WIND_EDGES_MPH, top_inclusive=True)
    wind = _apply_load_rules(wind_base, load_lb)
    parts = {
        "wind": (wind, wind_frac),
        "rain": _band(rain_in_hr, RAIN_EDGES_IN_HR, top_inclusive=False),
        "snow": _band(snow_in_hr, SNOW_EDGES_IN_HR, top_inclusive=False),
    }
    level = max(lvl for lvl, _ in parts.values())
    drivers = tuple(name for name, (lvl, _) in parts.items() if lvl == level) if level else ()
    score = max(min(float(lvl) + frac, 4.0) for lvl, frac in parts.values())
    return Assessment(
        level=level, drivers=drivers, load_adjusted=wind != wind_base, score=round(score, 2)
    )
