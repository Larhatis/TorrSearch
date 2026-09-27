from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedMovie
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 20, tzinfo=UTC)


class FakeTmdb:
    enabled = True

    async def get_details(self, media_type, tmdb_id):
        if tmdb_id == 693134:
            return MediaResult(
                tmdb_id=693134,
                media_type="movie",
                title="Dune : Deuxieme partie",
                original_title="Dune: Part Two",
                year="2024",
                overview="Paul Atreides s'unit a Chani...",
                poster_path="/dune.jpg",
            )
        return None


class _FakeJellyfin:
    base_url = "http://jelly"
    enabled = True

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)

    async def find_matching(self, title):
        return None


class FakeCtx:
    def __init__(self, jf=None):
        self.tmdb = FakeTmdb()
        self.config = Config(monitor=MonitorConfig(enabled=True))
        self.jellyfin = jf or _FakeJellyfin()


def _client(tmp_path, jf=None):
    movies = MovieLibrary(tmp_path / "lib.json")
    series = SeriesLibrary(tmp_path / "series.json")
    return TestClient(create_app(FakeCtx(jf=jf), library=movies, series_library=series)), movies


def test_movie_detail_modal_shows_info_and_search_links(tmp_path):
    client, movies = _client(tmp_path)
    movies.add(WantedMovie(tmdb_id=693134, title="Dune : Deuxieme partie", year="2024", added_at=NOW))
    resp = client.get("/movies/693134/detail", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    html = resp.text
    assert "Dune : Deuxieme partie" in html
    assert "Paul Atreides" in html
    assert "cat=movies" in html
    assert "1080p" in html
    assert "2160p" in html


def test_movie_detail_shows_jellyfin_status_and_link(tmp_path):
    jf = _FakeJellyfin(owned={"movie:693134": "jf-dune"})
    client, movies = _client(tmp_path, jf=jf)
    movies.add(WantedMovie(tmdb_id=693134, title="Dune : Deuxieme partie", year="2024", added_at=NOW))
    resp = client.get("/movies/693134/detail", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Dans Jellyfin" in resp.text
    assert "jf-dune" in resp.text


def test_movie_detail_full_page(tmp_path):
    client, movies = _client(tmp_path)
    movies.add(WantedMovie(tmdb_id=693134, title="Dune : Deuxieme partie", year="2024", added_at=NOW))
    resp = client.get("/movies/693134")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text
    assert "Dune : Deuxieme partie" in resp.text


def test_movie_detail_not_found_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/movies/999999")
    assert resp.status_code == 404


def test_movie_regrab_unmarks_movie(tmp_path):
    client, movies = _client(tmp_path)
    movies.add(WantedMovie(tmdb_id=693134, title="Dune", added_at=NOW))
    movies.mark_grabbed(693134, "Dune.Old.720p", NOW)
    assert movies.get(693134).status == "grabbed"

    resp = client.post("/movies/693134/regrab")
    assert resp.status_code == 200
    assert movies.get(693134).status == "wanted"
