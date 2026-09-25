import re

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.models import MediaResult
from torsearch.web.routes import create_app


class FakeTmdb:
    def __init__(self, enabled=True, results=None, movie_results=None, tv_results=None):
        self.enabled = enabled
        self._results = results or []
        self._movie_results = movie_results
        self._tv_results = tv_results

    async def search(self, query):
        return list(self._results)

    async def trending(self, media_type="all"):
        if media_type == "movie" and self._movie_results is not None:
            return list(self._movie_results)
        if media_type in ("tv", "series") and self._tv_results is not None:
            return list(self._tv_results)
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


class FakeMovieLibrary:
    def __init__(self):
        self._movies = []

    def list(self):
        return list(self._movies)

    def add(self, m):
        self._movies.append(m)
        return True


class FakeSeriesLibrary:
    def __init__(self):
        self._series = []

    def list(self):
        return list(self._series)

    def add(self, s):
        self._series.append(s)
        return True


def _client(tmdb, jellyfin=None, library=None, series_library=None) -> TestClient:
    return TestClient(create_app(FakeCtx(tmdb, jellyfin), library=library, series_library=series_library))


def _media():
    return MediaResult(tmdb_id=693134, media_type="movie", title="Dune Deux",
                       year="2024", overview="Paul...", poster_path="/a.jpg")


def _media_tv():
    return MediaResult(tmdb_id=1399, media_type="tv", title="Game of Thrones",
                       year="2011", overview="Neuf...", poster_path=None)


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
    assert 'href="/?q=Dune%20Deux%202024&cat=movies"' in resp.text
    assert "Torrents" in resp.text


def test_discover_card_tv_bridges_to_tv_category():
    resp = _client(FakeTmdb(results=[_media_tv()])).get("/discover/search", params={"q": "got"})
    assert 'href="/?q=Game%20of%20Thrones%202011&cat=tv"' in resp.text
    assert "Torrents" in resp.text


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


def test_discover_trending_renders_both_movie_and_series_sections():
    tmdb = FakeTmdb(movie_results=[_media()], tv_results=[_media_tv()])
    resp = _client(tmdb).get("/discover/trending")
    assert resp.status_code == 200
    assert "Films du moment" in resp.text
    assert "Dune Deux" in resp.text
    assert "Series du moment" in resp.text
    assert "Game of Thrones" in resp.text


def test_discover_trending_filters_by_tab():
    tmdb = FakeTmdb(movie_results=[_media()], tv_results=[_media_tv()])
    resp_movies = _client(tmdb).get("/discover/trending?tab=movie")
    assert resp_movies.status_code == 200
    assert "Dune Deux" in resp_movies.text
    assert "Game of Thrones" not in resp_movies.text

    resp_tv = _client(tmdb).get("/discover/trending?tab=tv")
    assert resp_tv.status_code == 200
    assert "Game of Thrones" in resp_tv.text
    assert "Dune Deux" not in resp_tv.text


def test_discover_marks_owned_in_jellyfin():
    jelly = FakeJellyfin(owned={"movie:693134": "item-xyz"})
    resp = _client(FakeTmdb(results=[_media()]), jelly).get("/discover/search", params={"q": "dune"})
    assert "Dans Jellyfin" in resp.text
    assert "item-xyz" in resp.text


def test_discover_poster_has_fallback_hook():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert "data-poster" in resp.text
    assert "onerror" not in resp.text


def test_discover_library_add_movie():
    lib = FakeMovieLibrary()
    resp = _client(FakeTmdb(results=[_media()]), library=lib).post(
        "/discover/library/add",
        data={
            "media_type": "movie",
            "tmdb_id": 693134,
            "title": "Dune Deux",
            "year": "2024",
            "poster_path": "/a.jpg",
        },
    )
    assert resp.status_code == 200
    assert "En bibliotheque" in resp.text
    assert len(lib.list()) == 1
    assert lib.list()[0].tmdb_id == 693134


def test_discover_library_add_series():
    series_lib = FakeSeriesLibrary()
    resp = _client(FakeTmdb(results=[_media_tv()]), series_library=series_lib).post(
        "/discover/library/add",
        data={
            "media_type": "tv",
            "tmdb_id": 1399,
            "title": "Game of Thrones",
            "year": "2011",
        },
    )
    assert resp.status_code == 200
    assert "En bibliotheque" in resp.text
    assert len(series_lib.list()) == 1
    assert series_lib.list()[0].tmdb_id == 1399


def test_discover_modal_renders_details():
    tmdb = FakeTmdb(results=[_media()])
    resp = _client(tmdb).get("/discover/movie/693134/modal")
    assert resp.status_code == 200
    assert "Dune Deux" in resp.text
    assert "Paul..." in resp.text
    assert "data-modal-close" in resp.text
    assert "Rechercher les torrents" in resp.text

