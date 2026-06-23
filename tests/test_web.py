import re

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
        self.dirs = []

    def add(self, download_url, download_dir=None):
        self.added.append(download_url)
        self.dirs.append(download_dir)
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


def test_search_renders_sort_control():
    client, _ = _make([_result("Anything")])
    resp = client.get("/search", params={"q": "x"})
    assert "hx-vals" in resp.text
    assert "Seeders" in resp.text


def test_index_shows_onboarding_when_no_trackers():
    service = SearchService([])
    ctx = FakeContext(service, FakeTransmission(), Config())  # no indexers
    client = TestClient(create_app(ctx))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Aucun tracker configure" in resp.text
    assert "/settings" in resp.text


def test_index_hides_onboarding_when_trackers_present():
    client, _ = _make()  # _make() seeds one indexer "t1"
    resp = client.get("/")
    assert "Aucun tracker configure" not in resp.text


def test_nav_marks_search_active():
    client, _ = _make()
    html = client.get("/").text
    assert re.search(r'href="/"[^>]*aria-current="page"', html)


def test_nav_marks_downloads_active():
    client, _ = _make()
    html = client.get("/downloads").text
    assert re.search(r'href="/downloads"[^>]*aria-current="page"', html)


def test_nav_keeps_logout_hidden_when_auth_disabled():
    client, _ = _make()
    assert "Deconnexion" not in client.get("/").text


def test_index_has_filter_panel_fields():
    client, _ = _make()
    html = client.get("/").text
    assert 'name="min_seeders"' in html
    assert 'name="quality"' in html
    assert 'name="exclude"' in html


def test_index_defines_clear_filter_helper():
    client, _ = _make()
    assert "function clearFilter" in client.get("/").text


def test_search_renders_quality_badge():
    client, _ = _make([_result("Film.2024.1080p.WEB")])
    resp = client.get("/search", params={"q": "x"})
    assert 'data-quality="1080p"' in resp.text


def test_search_renders_seeder_health():
    client, _ = _make([_result("Healthy", seeders=150), _result("Weak", seeders=5)])
    resp = client.get("/search", params={"q": "x"})
    assert 'data-health="good"' in resp.text
    assert 'data-health="low"' in resp.text


def test_search_shows_result_count():
    client, _ = _make([_result("One"), _result("Two")])
    resp = client.get("/search", params={"q": "x"})
    assert "2 resultat" in resp.text.lower()


def test_search_renders_active_filter_chip():
    client, _ = _make([_result("KeepMe", seeders=80)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "10"})
    assert 'data-filter="min_seeders"' in resp.text
    assert "clearFilter('min_seeders')" in resp.text


def test_download_routes_to_category_path():
    from torsearch.config import PathsConfig

    service = SearchService([FakeIndexer("t1", [])])
    transmission = FakeTransmission()
    config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")],
                    paths=PathsConfig(by_category={"movies": "/data/films"}))
    client = TestClient(create_app(FakeContext(service, transmission, config)))
    resp = client.post("/download", data={"download_url": "magnet:?x", "category": "movies"})
    assert resp.status_code == 200
    assert transmission.dirs == ["/data/films"]


def test_nav_labels_collapse_on_small_screens():
    client, _ = _make()
    assert "hidden lg:inline" in client.get("/").text


def test_download_toast_auto_dismisses():
    client, _ = _make()
    resp = client.post("/download", data={"download_url": "magnet:?x"})
    assert "toastfade" in resp.text
