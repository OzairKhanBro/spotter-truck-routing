from datetime import UTC, datetime, timedelta

import pytest

from trips.engine.forecast import HourlySeries, conditions_at

T0 = datetime(2026, 10, 14, 0, tzinfo=UTC)


def series(**overrides):
    base = {
        "times": [T0 + timedelta(hours=h) for h in range(4)],
        "wind_mph": [10.0, 20.0, 30.0, 40.0],
        "gust_mph": [15.0, 25.0, 35.0, 45.0],
        "rain_in": [0.0, 0.2, 0.4, 0.0],
        "snow_in": [0.0, 0.0, 0.0, 0.0],
    }
    base.update(overrides)
    return HourlySeries(**base)


def test_between_hours_wind_interpolates_and_rain_uses_containing_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1, minutes=30))
    assert c.wind_mph == pytest.approx(25.0)
    assert c.gust_mph == pytest.approx(30.0)
    assert c.rain_in_hr == 0.4  # hour ending 02:00 contains 01:30


def test_on_the_hour_uses_that_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1))
    assert c.wind_mph == 20.0
    assert c.rain_in_hr == 0.2


def test_tiny_float_noise_past_the_hour_does_not_jump_an_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1, microseconds=3))
    assert c.rain_in_hr == 0.2


def test_last_timestamp_is_inside_the_series():
    assert conditions_at(series(), T0 + timedelta(hours=3)).wind_mph == 40.0


@pytest.mark.parametrize("delta", [timedelta(minutes=-1), timedelta(hours=3, minutes=1)])
def test_outside_the_series_returns_none(delta):
    assert conditions_at(series(), T0 + delta) is None


def test_missing_values_return_none():
    s = series(wind_mph=[10.0, None, 30.0, 40.0])
    assert conditions_at(s, T0 + timedelta(minutes=30)) is None


def test_missing_gust_falls_back_to_wind():
    s = series(gust_mph=[None, None, None, None])
    assert conditions_at(s, T0).gust_mph == 10.0
