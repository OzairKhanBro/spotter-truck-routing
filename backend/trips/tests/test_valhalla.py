import itertools
import json
import math

import httpx
import polyline
import pytest
import respx
from django.conf import settings

from trips.engine.geo import haversine_mi
from trips.errors import NoRouteError, ProviderError
from trips.providers.valhalla import fetch_routes, parse_trip

CHI = (-87.63, 41.88)
DEN = (-104.99, 39.74)
MID_LAT = (CHI[1] + DEN[1]) / 2


def bent_line(a, b, bend_deg=0.0, n=60):
    """(lat, lon) pairs from a to b bowed north (+) or south (-) by bend_deg at the middle."""
    return [
        (
            a[1] + (b[1] - a[1]) * t + bend_deg * math.sin(math.pi * t),
            a[0] + (b[0] - a[0]) * t,
        )
        for t in (i / (n - 1) for i in range(n))
    ]


def trip_json(latlons, hours, name="I 80 W"):
    length = sum(haversine_mi((a[1], a[0]), (b[1], b[0])) for a, b in itertools.pairwise(latlons))
    last = len(latlons) - 1
    return {
        "legs": [
            {
                "shape": polyline.encode(latlons, 6),
                "maneuvers": [
                    {
                        "begin_shape_index": 0,
                        "end_shape_index": last // 2,
                        "time": hours * 1800,
                        "length": length / 2,
                        "street_names": [name],
                    },
                    {
                        "begin_shape_index": last // 2,
                        "end_shape_index": last,
                        "time": hours * 1800,
                        "length": length / 2,
                        "street_names": ["I 76"],
                    },
                    {"begin_shape_index": last, "end_shape_index": last, "time": 0, "length": 0},
                ],
            }
        ],
        "summary": {"length": length * 1.01, "time": hours * 3600},
    }


def body_of(request):
    return json.loads(request.content)


def test_parse_trip_spreads_maneuver_time_by_distance_and_scales_to_summary():
    route = parse_trip(trip_json(bent_line(CHI, DEN), hours=15))
    assert route.points[0] == pytest.approx(CHI, abs=1e-5)
    assert route.duration_s == pytest.approx(15 * 3600)
    assert route.distance_mi == pytest.approx(
        trip_json(bent_line(CHI, DEN), 15)["summary"]["length"]
    )
    assert all(b >= a for a, b in zip(route.cum_seconds, route.cum_seconds[1:]))
    assert route.label == "I 80 W · I 76"


@respx.mock
def test_uses_valhalla_alternates_when_it_returns_enough():
    call = respx.post(settings.VALHALLA_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "trip": trip_json(bent_line(CHI, DEN), 15),
                "alternates": [
                    {"trip": trip_json(bent_line(CHI, DEN, 1.5), 16)},
                    {"trip": trip_json(bent_line(CHI, DEN, -1.5), 16.5)},
                ],
            },
        )
    )
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 3
    assert call.call_count == 1
    sent = body_of(call.calls[0].request)
    assert sent["costing"] == "truck"
    assert sent["costing_options"]["truck"]["weight"] == pytest.approx(18.14, abs=0.01)
    assert sent["alternates"] == 2 and sent["units"] == "miles"


def is_primary(body):
    """The first request asks Valhalla for alternates; detour legs ask for none."""
    return body["alternates"] > 0


def leg_ends(body):
    a, b = body["locations"]
    return (a["lon"], a["lat"]), (b["lon"], b["lat"])


def _detour_handler(detour_hours):
    """Primary returns 1 alternate; each detour is two single-leg requests via an offset point."""

    def handler(request):
        body = body_of(request)
        assert len(body["locations"]) == 2
        if is_primary(body):
            return httpx.Response(
                200,
                json={
                    "trip": trip_json(bent_line(CHI, DEN), 15),
                    "alternates": [{"trip": trip_json(bent_line(CHI, DEN, 1.5), 16)}],
                },
            )
        assert body["alternates"] == 0
        start, end = leg_ends(body)
        return httpx.Response(
            200, json={"trip": trip_json(bent_line(start, end), detour_hours / 2)}
        )

    return handler


@respx.mock
def test_tops_up_with_a_detour_when_valhalla_returns_too_few():
    call = respx.post(settings.VALHALLA_URL).mock(side_effect=_detour_handler(detour_hours=18))
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 3
    assert call.call_count == 3  # primary + one detour as two legs
    first_leg, second_leg = (body_of(c.request) for c in call.calls[1:])
    origin, via = leg_ends(first_leg)
    via_again, destination = leg_ends(second_leg)
    assert origin == pytest.approx(CHI) and destination == pytest.approx(DEN)
    assert via == via_again
    detour = routes[2]
    assert detour.duration_s == pytest.approx(18 * 3600)
    assert detour.points[0] == pytest.approx(CHI, abs=1e-5)
    assert detour.points[-1] == pytest.approx(DEN, abs=1e-5)
    assert any(p == pytest.approx(via, abs=1e-5) for p in detour.points)
    assert all(b >= a for a, b in zip(detour.cum_seconds, detour.cum_seconds[1:]))
    assert all(b >= a for a, b in zip(detour.cum_miles, detour.cum_miles[1:]))


@respx.mock
def test_rejects_detours_that_are_far_slower():
    call = respx.post(settings.VALHALLA_URL).mock(side_effect=_detour_handler(detour_hours=40))
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 2
    assert call.call_count == 9  # primary + four detour attempts of two legs each


@respx.mock
def test_rejects_detours_that_duplicate_an_existing_route():
    base = bent_line(CHI, DEN)
    half = len(base) // 2

    def handler(request):
        body = body_of(request)
        if is_primary(body):
            return httpx.Response(200, json={"trip": trip_json(base, 15)})
        start, _ = leg_ends(body)
        leg = base[: half + 1] if start == pytest.approx(CHI) else base[half:]
        return httpx.Response(200, json={"trip": trip_json(leg, 7.6)})

    respx.post(settings.VALHALLA_URL).mock(side_effect=handler)
    assert len(fetch_routes(CHI, DEN, 40_000)) == 1


@respx.mock
def test_unroutable_detour_is_skipped():
    def handler(request):
        if is_primary(body_of(request)):
            return httpx.Response(200, json={"trip": trip_json(bent_line(CHI, DEN), 15)})
        return httpx.Response(400, json={"error_code": 171, "error": "No suitable edges"})

    call = respx.post(settings.VALHALLA_URL).mock(side_effect=handler)
    assert len(fetch_routes(CHI, DEN, 40_000)) == 1
    assert call.call_count == 5  # primary + four detours whose first leg fails


@respx.mock
def test_primary_over_distance_limit_names_the_limit():
    respx.post(settings.VALHALLA_URL).mock(
        return_value=httpx.Response(400, json={"error_code": 154, "error": "Path distance exceeds"})
    )
    with pytest.raises(NoRouteError, match="930 miles"):
        fetch_routes(CHI, (-122.42, 37.77), 40_000)


@respx.mock
def test_slow_routing_service_is_provider_error():
    respx.post(settings.VALHALLA_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError):
        fetch_routes(CHI, DEN, 40_000)


@respx.mock
def test_no_path_raises_no_route():
    respx.post(settings.VALHALLA_URL).mock(
        return_value=httpx.Response(
            400, json={"error_code": 442, "error": "No path could be found"}
        )
    )
    with pytest.raises(NoRouteError):
        fetch_routes(CHI, (-157.85, 21.30), 40_000)


@respx.mock
def test_server_error_is_provider_error():
    respx.post(settings.VALHALLA_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderError):
        fetch_routes(CHI, DEN, 40_000)
