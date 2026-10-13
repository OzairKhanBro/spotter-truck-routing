"""Hourly forecasts from Open-Meteo (no API key)."""

from datetime import UTC, datetime, timedelta
from itertools import batched

import httpx
from django.utils import timezone

from trips.engine.forecast import HourlySeries
from trips.engine.geo import LonLat
from trips.errors import ProviderError
from trips.models import ForecastCache

from .http import client_or_new

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
CELL_DEG = 0.1  # ~7 mi; keeps a long trip + corridor inside the free 600 locations/minute
BATCH_SIZE = 50
CACHE_TTL = timedelta(hours=1)

Key = tuple[float, float]


def cell_key(point: LonLat) -> Key:
    lon, lat = point
    return (
        round(round(lat / CELL_DEG) * CELL_DEG, 2),
        round(round(lon / CELL_DEG) * CELL_DEG, 2),
    )


def fetch_series(
    points: list[LonLat], *, client: httpx.Client | None = None, now: datetime | None = None
) -> list[HourlySeries]:
    now = now or timezone.now()
    keys = [cell_key(p) for p in points]
    wanted = set(keys)
    payloads: dict[Key, dict] = {
        (row.lat_key, row.lon_key): row.payload
        for row in ForecastCache.objects.filter(
            fetched_at__gte=now - CACHE_TTL, lat_key__in={k[0] for k in wanted}
        )
        if (row.lat_key, row.lon_key) in wanted
    }
    missing = [k for k in dict.fromkeys(keys) if k not in payloads]
    if missing:
        with client_or_new(client) as http:
            for batch in batched(missing, BATCH_SIZE):
                for key, payload in zip(batch, _request(http, batch)):
                    ForecastCache.objects.update_or_create(
                        lat_key=key[0],
                        lon_key=key[1],
                        defaults={"payload": payload, "fetched_at": now},
                    )
                    payloads[key] = payload
    series = {k: _to_series(payloads[k]) for k in wanted}
    return [series[k] for k in keys]


def _request(http: httpx.Client, batch: tuple[Key, ...]) -> list[dict]:
    params = {
        "latitude": ",".join(str(lat) for lat, _ in batch),
        "longitude": ",".join(str(lon) for _, lon in batch),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "past_days": 1,
        "forecast_days": 10,
    }
    try:
        response = http.get(OPEN_METEO_URL, params=params)
        if response.status_code == 429:
            raise ProviderError(
                "The weather service's free per-minute limit is used up. Try again in a minute."
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("The weather service didn't respond. Try again in a minute.") from exc
    locations = data if isinstance(data, list) else [data]
    return [_compact(loc["hourly"]) for loc in locations]


def _compact(hourly: dict) -> dict:
    rain = hourly["rain"]
    showers = hourly.get("showers") or [0.0] * len(rain)
    return {
        "time": hourly["time"],
        "wind": hourly["wind_speed_10m"],
        "gust": hourly["wind_gusts_10m"],
        # Rounded so 0.01 + 0.09 is 0.10 (Moderate), not 0.0999... (Low).
        "rain": [None if r is None else round(r + (s or 0.0), 4) for r, s in zip(rain, showers)],
        "snow": hourly["snowfall"],
    }


def _to_series(payload: dict) -> HourlySeries:
    return HourlySeries(
        times=[datetime.fromisoformat(t).replace(tzinfo=UTC) for t in payload["time"]],
        wind_mph=payload["wind"],
        gust_mph=payload["gust"],
        rain_in=payload["rain"],
        snow_in=payload["snow"],
    )
