import httpx
import respx

from trips.providers.photon import PHOTON_URL

DENVER = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {
                "name": "Denver",
                "state": "Colorado",
                "countrycode": "US",
                "city": "Denver",
            },
            "geometry": {"type": "Point", "coordinates": [-104.984862, 39.7392364]},
        }
    ],
}


@respx.mock
def test_geocode_returns_labelled_places(client):
    route = respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=DENVER))
    response = client.get("/api/geocode", {"q": "denver"})
    assert response.status_code == 200
    assert response.json() == [
        {"label": "Denver, Colorado, US", "lat": 39.73924, "lon": -104.98486}
    ]
    assert "bbox" in str(route.calls[0].request.url)


@respx.mock
def test_short_queries_skip_the_network(client):
    route = respx.get(PHOTON_URL)
    assert client.get("/api/geocode", {"q": "de"}).json() == []
    assert route.call_count == 0


@respx.mock
def test_geocoder_outage_is_502_with_message(client):
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(500))
    response = client.get("/api/geocode", {"q": "denver co"})
    assert response.status_code == 502
    assert "place search" in response.json()["detail"].lower()
