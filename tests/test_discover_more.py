from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedMovie, WantedSeries
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


def _m(i, kind="movie", title=None):
    return MediaResult(tmdb_id=i, media_type=kind, title=title or f"Titre {i}", year="2026")


class Tmdb:
    enabled = True

    def __init__(self):
        self.calls: list[tuple] = []

    async def genres(self, kind):
        return [(28, "Action")] if kind == "movie" else [(18, "Drame tele")]

    async def discover(self, kind, genre_id=None, year=None):
        self.calls.append(("discover", kind, genre_id, year))
        return [_m(100, kind)]

    async def upcoming(self):
        return [_m(200, title="Avatar 3")]

    async def recommendations(self, kind, tmdb_id):
        self.calls.append(("reco", kind, tmdb_id))
        # 1 is already watched, 2 is in Jellyfin, 3 is new (and suggested by both seeds)
        return [_m(1), _m(2), _m(3, title="Nouveau film")]


class Jelly:
    enabled = True
    base_url = "http://jf"

    async def owned(self):
        return {"movie:2": "x"}


class Ctx:
    def __init__(self):
        self.search_service = SearchService([])
        self.transmission = None
        self.config = Config()
        self.tmdb = Tmdb()
        self.jellyfin = Jelly()


def _client(tmp_path, seeded=True):
    movies, series = MovieLibrary(tmp_path / "m.json"), SeriesLibrary(tmp_path / "s.json")
    now = datetime.now(UTC)
    if seeded:
        movies.add(WantedMovie(tmdb_id=1, title="Dune", added_at=now - timedelta(days=1)))
        series.add(WantedSeries(tmdb_id=9, title="MobLand", added_at=now))
    ctx = Ctx()
    return TestClient(create_app(ctx, library=movies, series_library=series)), ctx


def test_page_has_filters_and_shortcuts(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover").text
    assert 'hx-get="/discover/upcoming"' in html and 'hx-get="/discover/for-you"' in html
    assert 'hx-get="/discover/genre-options"' in html and 'hx-trigger="load"' in html
    assert 'name="year"' in html
    assert '<option value="28">Action</option>' in client.get("/discover/genre-options").text
    assert "Drame tele" in client.get("/discover/genre-options", params={"type": "tv"}).text


def test_browse_applies_filters(tmp_path):
    client, ctx = _client(tmp_path)
    html = client.get("/discover/browse", params={"type": "movie", "genre": "28", "year": "2024"}).text
    assert ("discover", "movie", 28, 2024) in ctx.tmdb.calls
    assert "Films · Action · 2024" in html and "Titre 100" in html
    client.get("/discover/browse", params={"type": "tv", "genre": "abc", "year": "../x"})
    assert ("discover", "tv", None, None) in ctx.tmdb.calls  # junk filters ignored


def test_upcoming_section(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover/upcoming").text
    assert "Bientot au cinema en France" in html and "Avatar 3" in html


def test_for_you_skips_known_titles_and_duplicates(tmp_path):
    client, ctx = _client(tmp_path)
    html = client.get("/discover/for-you").text
    assert [c for c in ctx.tmdb.calls if c[0] == "reco"] == [("reco", "tv", 9), ("reco", "movie", 1)]
    assert "Parce que tu as ajoute « MobLand »" in html
    assert html.count("Nouveau film") >= 1 and "Titre 1<" not in html and "Titre 2<" not in html
    assert "Parce que tu as ajoute « Dune »" not in html  # its only fresh title was already shown


def test_for_you_without_library(tmp_path):
    client, _ = _client(tmp_path, seeded=False)
    assert "Ajoute des films ou des series" in client.get("/discover/for-you").text
