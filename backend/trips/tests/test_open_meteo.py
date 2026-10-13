from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from trips.engine.risk import Level, assess
from trips.errors import ProviderError
from trips.models import ForecastCache
from trips.providers.open_meteo import OPEN_METEO_URL, fetch_series


def _location(lat: float, lon: float) -> dict:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": {
            "time": ["2026-10-14T00:00", "2026-10-14T01:00"],
            "wind_speed_10m": [12.0, 14.0],
            "wind_gusts_10m": [20.0, 22.0],
            "rain": [0.05, 0.10],
            "showers": [0.05, None],
            "snowfall": [0.0, 0.2],
        },
    }


def _handler(request: httpx.Request) -> httpx.Response:
    q = parse_qs(urlparse(str(request.url)).query)
    lats = [float(x) for x in q["latitude"][0].split(",")]
    lons = [float(x) for x in q["longitude"][0].split(",")]
    body = [_location(a, o) for a, o in zip(lats, lons)]
    return httpx.Response(200, json=body if len(body) > 1 else body[0])


@pytest.mark.django_db
@respx.mock
def test_fetches_unique_cells_once_and_caches():
    route = respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    points = [(-87.63, 41.88), (-104.99, 39.74), (-87.631, 41.881)]  # 1st and 3rd share a cell

    series = fetch_series(points)

    assert len(series) == 3
    assert route.call_count == 1
    q = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert len(q["latitude"][0].split(",")) == 2
    assert q["wind_speed_unit"] == ["mph"] and q["precipitation_unit"] == ["inch"]
    assert series[0] == series[2]
    assert ForecastCache.objects.count() == 2

    fetch_series(points)
    assert route.call_count == 1  # served from cache


@pytest.mark.django_db
@respx.mock
def test_rain_includes_showers_and_times_are_utc():
    respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    s = fetch_series([(-87.63, 41.88)])[0]
    assert s.rain_in == [pytest.approx(0.10), pytest.approx(0.10)]  # None showers count as 0
    assert s.snow_in == [0.0, 0.2]
    assert s.times[0].tzinfo is not None and s.times[0].utcoffset().total_seconds() == 0


@pytest.mark.django_db
@respx.mock
def test_batches_of_fifty():
    route = respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    points = [(-100 + i * 0.2, 40.0) for i in range(120)]
    assert len(fetch_series(points)) == 120
    assert route.call_count == 3


@pytest.mark.django_db
@respx.mock
def test_upstream_failure_is_a_provider_error():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderError) as exc:
        fetch_series([(-87.63, 41.88)])
    assert exc.value.status == 502
    assert "weather service" in exc.value.message.lower()


@pytest.mark.django_db
@respx.mock
def test_rate_limit_names_the_per_minute_limit():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(429, json={"reason": "limit"}))
    with pytest.raises(ProviderError) as exc:
        fetch_series([(-87.63, 41.88)])
    assert exc.value.status == 502
    assert "per-minute limit" in exc.value.message


@pytest.mark.django_db
@respx.mock
def test_slow_weather_service_is_a_provider_error():
    respx.get(OPEN_METEO_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError) as exc:
        fetch_series([(-87.63, 41.88)])
    assert exc.value.status == 502


@pytest.mark.django_db
@respx.mock
def test_rain_plus_showers_on_a_band_edge_lands_in_the_documented_band():
    # 0.01 + 0.09 is 0.09999999999999999 in floating point; the driver expects Moderate.
    def handler(request):
        loc = _location(41.9, -87.6)
        loc["hourly"]["rain"] = [0.01, 0.01]
        loc["hourly"]["showers"] = [0.09, 0.09]
        return httpx.Response(200, json=loc)

    respx.get(OPEN_METEO_URL).mock(side_effect=handler)
    s = fetch_series([(-87.63, 41.88)])[0]
    assert s.rain_in[0] == 0.10
    assert (
        assess(wind_mph=0, rain_in_hr=s.rain_in[0], snow_in_hr=0, load_lb=1).level == Level.MODERATE
    )
