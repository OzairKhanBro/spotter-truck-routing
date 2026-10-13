from datetime import timedelta

import pytest
from django.utils import timezone

from trips import services
from trips.engine.corridor import MAX_ACTIVE, build_grid, corridor_scores
from trips.engine.geo import haversine_mi
from trips.errors import ProviderError
from trips.tests.factories import flat_series, floor_hour
from trips.tests.test_trips_api import fake_routes, fake_series, payload, post

LINE = [(-100.0 + i * 0.05, 40.0) for i in range(41)]  # ~105 mi east-west


def test_grid_covers_route_with_buffer_and_masks_far_cells():
    g = build_grid([LINE], cell_mi=20, buffer_mi=40)
    assert g.west < -100 and g.east > -98 and g.south < 40 < g.north
    assert 0 < len(g.active) < g.cols * g.rows
    for lon, lat in g.centers:
        nearest = min(haversine_mi((lon, lat), p) for p in LINE)
        assert nearest <= 40 + 20 * 1.5  # buffer plus a cell diagonal


def test_grid_is_capped_for_long_routes():
    coast_to_coast = [(-122.0 + i * 0.5, 37.0 + (i % 3) * 0.3) for i in range(100)]
    g = build_grid([coast_to_coast])
    assert g.cols * g.rows <= 2500
    assert len(g.active) <= MAX_ACTIVE == 250  # Open-Meteo free tier: 600 locations/minute


def test_scores_have_49_frames_and_mask_inactive_cells():
    g = build_grid([LINE])
    start = floor_hour(timezone.now())
    series = [flat_series(start - timedelta(hours=1), wind=40.0) for _ in g.centers]
    frames = corridor_scores(g, series, start, load_lb=45_000)
    assert len(frames) == 49
    assert all(len(f) == g.cols * g.rows for f in frames)
    inactive = set(range(g.cols * g.rows)) - set(g.active)
    assert all(frames[0][i] == -1 for i in inactive)
    assert all(3 <= frames[0][i] < 4 for i in g.active)  # 40 mph + 45k lb = Severe


@pytest.mark.django_db
def test_corridor_endpoint_builds_once_then_reuses(client, monkeypatch):
    calls = []
    monkeypatch.setattr(services, "fetch_routes", fake_routes)

    def counting_series(points, now=None):
        calls.append(len(points))
        return fake_series(points)

    monkeypatch.setattr(services, "fetch_series", counting_series)
    trip = post(client, payload()).json()
    before = len(calls)

    first = client.get(f"/api/trips/{trip['id']}/corridor").json()
    second = client.get(f"/api/trips/{trip['id']}/corridor").json()

    assert first == second
    assert len(calls) == before + 1
    assert first["start"] == trip["timeline_start"]
    assert len(first["scores"]) == 49
    assert len(first["scores"][0]) == first["cols"] * first["rows"]


@pytest.mark.django_db
def test_corridor_weather_outage_is_502(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)
    monkeypatch.setattr(services, "fetch_series", fake_series)
    trip = post(client, payload()).json()

    def down(points, now=None):
        raise ProviderError("The weather service didn't respond. Try again in a minute.")

    monkeypatch.setattr(services, "fetch_series", down)
    response = client.get(f"/api/trips/{trip['id']}/corridor")
    assert response.status_code == 502
    assert "weather service" in response.json()["detail"]
