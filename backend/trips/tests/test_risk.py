import math

import pytest

from trips.engine.risk import Level, assess

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


def level(wind=0.0, rain=0.0, snow=0.0, load=20_000):
    return assess(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=load).level


@pytest.mark.parametrize(
    "wind,expected",
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34.9, M),
        (35, H),
        (44.9, H),
        (45, S),
        (54.9, S),
        (55, N),
        (80, N),
    ],
)
def test_wind_bands_with_light_load(wind, expected):
    assert level(wind=wind, load=10_000) == expected


@pytest.mark.parametrize(
    "rain,expected",
    [(0.09, L), (0.10, M), (0.24, M), (0.25, H), (0.49, H), (0.50, S), (1.00, S), (1.01, N)],
)
def test_rain_bands(rain, expected):
    assert level(rain=rain) == expected


@pytest.mark.parametrize(
    "snow,expected",
    [(0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_bands(snow, expected):
    assert level(snow=snow) == expected


@pytest.mark.parametrize(
    "wind,load,expected",
    [
        (60, 1_000, N),  # >=55 is No Travel for any load
        (50, 30_000, S),  # exactly 30,000 is not "more than"
        (50, 30_001, N),  # 45-54 + >30,000 -> No Travel
        (40, 40_000, H),  # exactly 40,000 is not "more than"
        (40, 40_001, S),  # 35-44 + >40,000 -> Severe
        (40, 35_000, H),  # heavy-ish but under the 40k rule
        (30, 80_000, M),  # load rules never touch Moderate wind
    ],
)
def test_load_rules(wind, load, expected):
    assert level(wind=wind, load=load) == expected


def test_worst_condition_wins_and_is_named():
    a = assess(wind_mph=30, rain_in_hr=0.6, snow_in_hr=0, load_lb=10_000)
    assert a.level == S
    assert a.drivers == ("rain",)


def test_tied_conditions_are_all_named():
    a = assess(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0, load_lb=10_000)
    assert a.level == H
    assert a.drivers == ("wind", "rain")


def test_low_has_no_drivers():
    assert assess(wind_mph=5, rain_in_hr=0, snow_in_hr=0, load_lb=10_000).drivers == ()


def test_load_adjusted_flag():
    assert assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=45_000).load_adjusted
    assert not assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=5_000).load_adjusted


def test_negative_inputs_are_treated_as_zero():
    assert level(wind=-3, rain=-0.1, snow=-1) == L


def test_score_floor_always_matches_level():
    for wind10 in range(0, 700, 7):
        for rain100 in (0, 10, 30, 75, 120):
            for load in (20_000, 45_000):
                a = assess(
                    wind_mph=wind10 / 10, rain_in_hr=rain100 / 100, snow_in_hr=0, load_lb=load
                )
                assert math.floor(a.score) == a.level
                assert 0 <= a.score <= 4
