import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests are hermetic: respx or monkeypatch must stand in for every upstream call."""

    def refuse(*args, **kwargs):
        raise RuntimeError("Tests must not open network connections; mock the provider.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
