def test_client_routes_serve_the_spa(client, settings, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    settings.FRONTEND_DIST = tmp_path
    response = client.get("/trips/abc")
    assert response.status_code == 200
    assert b"id=root" in b"".join(response.streaming_content)


def test_missing_build_is_404(client, settings, tmp_path):
    settings.FRONTEND_DIST = tmp_path / "nope"
    assert client.get("/").status_code == 404
