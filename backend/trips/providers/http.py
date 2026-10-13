from contextlib import nullcontext

import httpx
from django.conf import settings


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0, connect=5.0),
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )


def client_or_new(client: httpx.Client | None):
    """Use the caller's client without closing it, or open and close a new one."""
    return nullcontext(client) if client is not None else http_client()
