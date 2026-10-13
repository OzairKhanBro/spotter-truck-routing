from datetime import UTC, timedelta

import httpx
import pytest
import respx
from django.conf import settings
from django.utils import timezone

from trips import services
from trips.errors import NoRouteError, ProviderError
from trips.tests.factories import flat_series, floor_hour, straight_route

ORIGIN = {"label": "Origin", "lat": 40.0, "lon": -100.0}
DEST = {"label": "Destination", "lat": 40.0, "lon": -98.0}


def fake_routes(origin, destination, load_lb):
    return [
        straight_route("A road", (-100, 40.0), (-98, 40.0), hours=2.0),
        straight_route("B road", (-100, 40.0), (-98, 40.6), hours=2.5),
        straight_route("C road", (-100, 40.0), (-98, 39.4), hours=1.8),
    ]


def fake_series(points, now=None):
    start = floor_hour(timezone.now()) - timedelta(days=1)
    # South of 39.8° is windy: 40 mph is High, and Severe for loads over 40,000 lb.
    return [flat_series(start, wind=40.0 if lat < 39.8 else 5.0) for lon, lat in points]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)
    monkeypatch.setattr(services, "fetch_series", fake_series)


def payload(**overrides):
    body = {
        "origin": ORIGIN,
        "destination": DEST,
        "departure": (timezone.now() + timedelta(hours=2)).isoformat(),
        "load_lb": 45_000,
        "interval_mi": 25,
    }
    body.update(overrides)
    return body


def post(client, body):
    return client.post("/api/trips", body, content_type="application/json")


@pytest.mark.django_db
def test_plans_three_routes_and_recommends_the_safe_fast_one(client, fakes):
    response = post(client, payload())
    assert response.status_code == 201
    trip = response.json()
    assert [r["id"] for r in trip["routes"]] == ["A", "B", "C"]
    rec = trip["recommendation"]
    assert rec["route_id"] == "A"
    assert rec["reason"] == "Same risk as Route B, 30 min faster."
    assert {r["id"]: r["rank"] for r in trip["routes"]} == {"A": 1, "B": 2, "C": 3}
    c = trip["routes"][2]
    assert c["summary"]["miles_by_level"]["severe"] > 0
    assert any(cp["load_adjusted"] for cp in c["checkpoints"])


@pytest.mark.django_db
def test_checkpoints_carry_eta_and_conditions(client, fakes):
    body = payload(interval_mi=10)
    trip = post(client, body).json()
    a = trip["routes"][0]
    miles = [cp["mile"] for cp in a["checkpoints"]]
    assert miles[:3] == [0, 10, 20] and miles[-1] == a["distance_mi"]
    assert a["checkpoints"][0]["eta"] == trip["departure"]
    assert a["checkpoints"][-1]["eta"] == a["arrival"]
    assert a["segments"][0]["coordinates"][0] == [-100.0, 40.0]
    assert len(a["path"]["coordinates"]) == len(a["path"]["seconds"])


@pytest.mark.django_db
def test_departure_with_offset_is_stored_as_utc(client, fakes):
    local = (timezone.now() + timedelta(days=1)).astimezone(timezone.get_fixed_timezone(-300))
    local = local.replace(minute=0, second=0, microsecond=0)
    trip = post(client, payload(departure=local.isoformat())).json()
    assert trip["departure"] == local.astimezone(UTC).isoformat()
    assert trip["timeline_start"] == trip["departure"]


@pytest.mark.django_db
def test_get_returns_the_saved_trip(client, fakes):
    created = post(client, payload()).json()
    fetched = client.get(f"/api/trips/{created['id']}").json()
    assert fetched == created


@pytest.mark.django_db
def test_unknown_trip_is_404(client):
    assert client.get("/api/trips/00000000-0000-0000-0000-000000000000").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"departure": "2020-01-01T00:00:00Z"}, "Departure is in the past"),
        ({"departure": "2099-01-01T00:00:00Z"}, "within the next 7 days"),
        ({"destination": ORIGIN}, "same place"),
    ],
)
def test_rejects_unplannable_trips(client, fakes, overrides, message):
    response = post(client, payload(**overrides))
    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"load_lb": 0},
        {"load_lb": 150_001},
        {"interval_mi": 30},
        {"departure": "2026-10-14T06:00:00"},  # no offset
    ],
)
def test_schema_validation(client, fakes, overrides):
    assert post(client, payload(**overrides)).status_code == 422


@pytest.mark.django_db
def test_trip_ending_past_the_forecast_is_422(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)
    short = lambda points, now=None: [
        flat_series(floor_hour(timezone.now()) - timedelta(hours=1), hours=3) for _ in points
    ]
    monkeypatch.setattr(services, "fetch_series", short)
    response = post(client, payload(departure=(timezone.now() + timedelta(hours=1)).isoformat()))
    assert response.status_code == 422
    assert "beyond the forecast" in response.json()["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error,status", [(NoRouteError("No truck route"), 422), (ProviderError("down"), 502)]
)
def test_provider_errors_surface_with_message(client, monkeypatch, error, status):
    def boom(*args, **kwargs):
        raise error

    monkeypatch.setattr(services, "fetch_routes", boom)
    response = post(client, payload())
    assert response.status_code == status
    assert response.json()["detail"] == error.message


@pytest.mark.django_db
def test_fewer_than_three_routes_adds_a_note(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", lambda *a: fake_routes(*a)[:2])
    monkeypatch.setattr(services, "fetch_series", fake_series)
    trip = post(client, payload()).json()
    assert len(trip["routes"]) == 2
    assert trip["notes"] == ["Only 2 distinct truck routes exist between these places."]


@pytest.mark.django_db
def test_every_route_blocked_still_recommends_the_least_bad(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)

    def gale(points, now=None):
        start = floor_hour(timezone.now()) - timedelta(days=1)
        return [flat_series(start, wind=60.0) for _ in points]

    monkeypatch.setattr(services, "fetch_series", gale)
    response = post(client, payload())
    assert response.status_code == 201
    trip = response.json()
    assert trip["recommendation"]["all_blocked"] is True
    assert sorted(r["rank"] for r in trip["routes"]) == [1, 2, 3]
    assert all(r["summary"]["max_level"] == "no_travel" for r in trip["routes"])
    assert trip["recommendation"]["route_id"] in {"A", "B", "C"}


@pytest.mark.django_db
def test_weather_outage_is_502_with_message(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)

    def down(points, now=None):
        raise ProviderError("The weather service didn't respond. Try again in a minute.")

    monkeypatch.setattr(services, "fetch_series", down)
    response = post(client, payload())
    assert response.status_code == 502
    assert "weather service" in response.json()["detail"]


@pytest.mark.django_db
@respx.mock
def test_routing_timeout_end_to_end_is_502_not_500(client):
    respx.post(settings.VALHALLA_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    response = post(client, payload())
    assert response.status_code == 502
    assert "routing service" in response.json()["detail"]
