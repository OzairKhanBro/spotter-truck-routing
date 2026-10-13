import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HourlySeries:
    """Hourly forecast for one location. `times` are UTC and one hour apart.

    `rain_in` and `snow_in` are totals for the hour ENDING at each timestamp
    (Open-Meteo's convention), so they read directly as in/hr.
    """

    times: list[datetime]
    wind_mph: list[float | None]
    gust_mph: list[float | None]
    rain_in: list[float | None]
    snow_in: list[float | None]


@dataclass(frozen=True)
class Conditions:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float


def conditions_at(series: HourlySeries, when: datetime) -> Conditions | None:
    """Weather the truck meets at `when`, or None if the forecast doesn't cover it."""
    if not series.times:
        return None
    hours = round((when - series.times[0]).total_seconds() / 3600, 6)
    last = len(series.times) - 1
    if hours < 0 or hours > last:
        return None
    i, frac = math.floor(hours), hours - math.floor(hours)
    containing = math.ceil(hours)

    def instantaneous(values: list[float | None]) -> float | None:
        a, b = values[i], values[min(i + 1, last)]
        if a is None or b is None:
            return None
        return a + (b - a) * frac

    wind = instantaneous(series.wind_mph)
    gust = instantaneous(series.gust_mph)
    rain = series.rain_in[containing]
    snow = series.snow_in[containing]
    if wind is None or rain is None or snow is None:
        return None
    return Conditions(
        wind_mph=round(wind, 1),
        gust_mph=round(gust if gust is not None else wind, 1),
        rain_in_hr=rain,
        snow_in_hr=snow,
    )
