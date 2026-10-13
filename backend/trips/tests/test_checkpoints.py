import pytest

from trips.engine.checkpoints import checkpoint_miles, place_checkpoints, slice_path, thin
from trips.engine.geo import haversine_mi, locate, offset_mi
from trips.engine.route import RouteGeometry
from trips.tests.factories import straight_route


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_mi((0, 0), (1, 0)) == pytest.approx(69.09, abs=0.05)


def test_locate_handles_ends_and_middle():
    cum = [0.0, 10.0, 30.0]
    assert locate(cum, -5) == (0, 0.0)
    assert locate(cum, 20) == (1, 0.5)
    assert locate(cum, 99) == (1, 1.0)


def test_offset_moves_north_and_east():
    lon, lat = offset_mi((-100.0, 40.0), east_mi=0, north_mi=69.0)
    assert (lon, lat) == pytest.approx((-100.0, 41.0))


@pytest.mark.parametrize(
    "total,interval,expected",
    [
        (60, 25, [0, 25, 50, 60]),
        (50, 25, [0, 25, 50]),
        (0, 10, [0]),
        (0.3, 50, [0, 0.3]),
        (120, 50, [0, 50, 100, 120]),
    ],
)
def test_checkpoint_miles_always_include_origin_and_destination(total, interval, expected):
    assert checkpoint_miles(total, interval) == expected


def test_checkpoint_miles_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        checkpoint_miles(100, 0)


def _two_speed_route() -> RouteGeometry:
    # 200 miles: first 100 mi take 2 h, second 100 mi take 1 h.
    return RouteGeometry(
        label="test",
        points=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)],
        cum_miles=[0.0, 100.0, 200.0],
        cum_seconds=[0.0, 7200.0, 10800.0],
    )


def test_checkpoint_offsets_follow_drive_time_not_distance():
    cps = place_checkpoints(_two_speed_route(), 50)
    assert [c.mile for c in cps] == [0, 50, 100, 150, 200]
    assert [c.offset_s for c in cps] == [0, 3600, 7200, 9000, 10800]
    assert (cps[1].lon, cps[1].lat) == pytest.approx((0.5, 0.0))


def test_thin_keeps_endpoints_and_spacing():
    route = straight_route("A", (-100, 40), (-98, 40), hours=2, n=400)
    t = thin(route, step_mi=5)
    assert t.points[0] == route.points[0] and t.points[-1] == route.points[-1]
    assert t.distance_mi == route.distance_mi
    gaps = [b - a for a, b in zip(t.cum_miles, t.cum_miles[1:-1])]
    assert all(g >= 5 for g in gaps)


def test_slice_path_interpolates_its_ends():
    path = slice_path(_two_speed_route(), 50, 150)
    assert path[0] == pytest.approx((0.5, 0.0))
    assert path[1] == (1.0, 0.0)
    assert path[-1] == pytest.approx((1.5, 0.0))
