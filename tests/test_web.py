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


def _result(title, size=1000, seeders=10, leechers=1):
    return SearchResult(
        title=title, size=size, seeders=seeders, leechers=leechers,
        source="t1", category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:" + title.replace(" ", "_"),
    )


def test_search_applies_min_seeders_filter():
    client, _ = _make([_result("LowSeed", seeders=2), _result("HighSeed", seeders=80)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "10"})
    assert resp.status_code == 200
    assert "HighSeed" in resp.text
    assert "LowSeed" not in resp.text


def test_search_quality_filter():
    client, _ = _make([_result("Film 1080p BluRay"), _result("Film 720p WEB")])
    resp = client.get("/search", params={"q": "x", "quality": "1080p"})
    assert "1080p BluRay" in resp.text
    assert "720p WEB" not in resp.text


def test_search_exclude_word():
    client, _ = _make([_result("Film CAM"), _result("Film Clean 1080p")])
    resp = client.get("/search", params={"q": "x", "exclude": "cam"})
    assert "Film Clean 1080p" in resp.text
    assert "Film CAM" not in resp.text


def test_search_sort_size_ascending():
    client, _ = _make([_result("BigOne", size=3_000_000_000), _result("SmallOne", size=1_000_000_000)])
    resp = client.get("/search", params={"q": "x", "sort": "size", "dir": "asc"})
    assert resp.text.index("SmallOne") < resp.text.index("BigOne")


def test_search_invalid_filter_params_do_not_500():
    client, _ = _make([_result("KeepMe", seeders=5)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "abc", "min_size_gb": "xyz"})
    assert resp.status_code == 200
    assert "KeepMe" in resp.text


def test_search_renders_sortable_headers():
    client, _ = _make([_result("Anything")])
    resp = client.get("/search", params={"q": "x"})
    assert "hx-vals" in resp.text
    assert "Seed" in resp.text
