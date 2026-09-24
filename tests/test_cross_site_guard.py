from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


class _Transmission:
    def __init__(self):
        self.added = []

    async def add(self, download_url, download_dir=None):
        self.added.append(download_url)
        return 1


class _Ctx:
    def __init__(self):
        self.search_service = SearchService([])
        self.transmission = _Transmission()
        self.config = Config()


def _client():
    ctx = _Ctx()
    return TestClient(create_app(ctx)), ctx.transmission  # auth disabled: the riskiest mode


def test_cross_site_post_is_refused():
    client, transmission = _client()
    resp = client.post("/download", data={"download_url": "magnet:?x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403
    assert transmission.added == []


def test_same_site_post_is_refused():
    client, transmission = _client()
    resp = client.post("/download", data={"download_url": "magnet:?x"}, headers={"Sec-Fetch-Site": "same-site"})
    assert resp.status_code == 403
    assert transmission.added == []


def test_same_origin_post_is_allowed():
    client, transmission = _client()
    resp = client.post("/download", data={"download_url": "magnet:?x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert resp.status_code == 200
    assert transmission.added == ["magnet:?x"]


def test_post_without_fetch_metadata_is_allowed():
    client, transmission = _client()  # curl, scripts, old browsers
    assert client.post("/download", data={"download_url": "magnet:?x"}).status_code == 200
    assert transmission.added == ["magnet:?x"]


def test_cross_site_navigation_is_allowed():
    client, _ = _client()
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
