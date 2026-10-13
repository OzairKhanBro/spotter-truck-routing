"""Place search via Photon (komoot, OSM data, no key)."""

import httpx
from django.core.cache import cache

from trips.errors import ProviderError

from .http import client_or_new

PHOTON_URL = "https://photon.komoot.io/api/"
NORTH_AMERICA_BBOX = "-170,15,-50,72"
CACHE_SECONDS = 24 * 3600


def search_places(q: str, *, client: httpx.Client | None = None) -> list[dict]:
    q = q.strip()
    if len(q) < 3:
        return []
    cache_key = f"photon:{q.lower()}"
    if (hit := cache.get(cache_key)) is not None:
        return hit
    with client_or_new(client) as http:
        try:
            response = http.get(
                PHOTON_URL, params={"q": q, "limit": 6, "lang": "en", "bbox": NORTH_AMERICA_BBOX}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError("Place search isn't responding. Try again in a minute.") from exc
    places = [_place(f) for f in response.json().get("features", [])]
    cache.set(cache_key, places, CACHE_SECONDS)
    return places


def _place(feature: dict) -> dict:
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    parts = [props.get(k) for k in ("name", "city", "state", "countrycode")]
    label = ", ".join(dict.fromkeys(p for p in parts if p))
    return {"label": label, "lat": round(lat, 5), "lon": round(lon, 5)}
