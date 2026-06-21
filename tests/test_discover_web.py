import json
import re

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.models import MediaResult
from torsearch.web.routes import create_app


class FakeTmdb:
    def __init__(self, enabled=True, results=None):
        self.enabled = enabled
        self._results = results or []

    async def search(self, query):
        return list(self._results)

    async def trending(self):
        return list(self._results)


class FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)


class FakeCtx:
    def __init__(self, tmdb, jellyfin=None):
        self.tmdb = tmdb
        self.config = Config()
        self.jellyfin = jellyfin or FakeJellyfin()


def _client(tmdb, jellyfin=None) -> TestClient:
    return TestClient(create_app(FakeCtx(tmdb, jellyfin)))


def _media():
    return MediaResult(tmdb_id=693134, media_type="movie", title="Dune Deux",
                       year="2024", overview="Paul...", poster_path="/a.jpg")


def test_discover_page_shows_onboarding_without_key():
    resp = _client(FakeTmdb(enabled=False)).get("/discover")
    assert resp.status_code == 200
    assert "TMDB_API_KEY" in resp.text


def test_discover_page_shows_search_with_key():
    resp = _client(FakeTmdb(enabled=True)).get("/discover")
    assert resp.status_code == 200
    assert 'hx-get="/discover/search"' in resp.text


def test_discover_search_renders_media_cards():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert resp.status_code == 200
    assert "Dune Deux" in resp.text
    assert "2024" in resp.text


def test_discover_card_bridges_to_torrent_search():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert 'hx-get="/search"' in resp.text
    assert "Torrents" in resp.text


def test_discover_card_hx_vals_is_valid_json_with_query():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    match = re.search(r"hx-vals='([^']*)'", resp.text)
    assert match, "hx-vals must be single-quoted and present"
    data = json.loads(match.group(1))
    assert data["q"] == "Dune Deux 2024"
    assert data["cat"] == "movies"


def test_discover_search_empty_query_shows_placeholder():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "  "})
    assert "Aucun media" in resp.text


def test_nav_marks_discover_active():
    html = _client(FakeTmdb(enabled=True)).get("/discover").text
    assert re.search(r'href="/discover"[^>]*aria-current="page"', html)


def test_discover_page_autoloads_trending():
    resp = _client(FakeTmdb(enabled=True)).get("/discover")
    assert 'hx-get="/discover/trending"' in resp.text


def test_discover_trending_renders_cards():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/trending")
    assert resp.status_code == 200
    assert "Dune Deux" in resp.text


def test_discover_marks_owned_in_jellyfin():
    jelly = FakeJellyfin(owned={"movie:693134": "item-xyz"})
    resp = _client(FakeTmdb(results=[_media()]), jelly).get("/discover/search", params={"q": "dune"})
    assert "Dans Jellyfin" in resp.text
    assert "item-xyz" in resp.text
