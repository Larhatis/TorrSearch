from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


class FakeIndexer:
    def __init__(self, name, results=None):
        self.name = name
        self.enabled = True
        self._results = results or []

    async def search(self, query, category):
        return list(self._results)


class FakeTransmission:
    def __init__(self):
        self.added = []

    def add(self, download_url):
        self.added.append(download_url)
        return 7


class FakeContext:
    def __init__(self, search_service, transmission, config):
        self.search_service = search_service
        self.transmission = transmission
        self.config = config


def _make(results=None):
    service = SearchService([FakeIndexer("t1", results or [])])
    transmission = FakeTransmission()
    config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")])
    client = TestClient(create_app(FakeContext(service, transmission, config)))
    return client, transmission


def _movie():
    return SearchResult(
        title="Cool.Movie.2024", size=2147483648, seeders=99, leechers=3,
        source="t1", category=Category.MOVIES, download_url="magnet:?xt=urn:btih:ABC",
    )


def test_index_renders_search_form():
    client, _ = _make()
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'name="q"' in resp.text


def test_search_renders_result_rows():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "cool", "cat": "all"})
    assert resp.status_code == 200
    assert "Cool.Movie.2024" in resp.text
    assert "99" in resp.text


def test_search_empty_query_shows_placeholder():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "   "})
    assert resp.status_code == 200
    assert "Aucun" in resp.text


def test_download_sends_to_transmission():
    client, transmission = _make()
    resp = client.post("/download", data={"download_url": "magnet:?xt=urn:btih:XYZ"})
    assert resp.status_code == 200
    assert transmission.added == ["magnet:?xt=urn:btih:XYZ"]
    assert "Transmission" in resp.text
