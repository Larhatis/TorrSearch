from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedSeries
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 21, tzinfo=UTC)


class FakeTmdb:
    enabled = True

    async def search(self, query):
        return [
            MediaResult(tmdb_id=1399, media_type="tv", title="Game of Thrones", year="2011",
                        poster_path="/g.jpg"),
        ]


class _FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)


class FakeCtx:
    def __init__(self):
        self.tmdb = FakeTmdb()
        self.config = Config(monitor=MonitorConfig(enabled=True))
        self.jellyfin = _FakeJellyfin()


def _client(tmp_path):
    movies = MovieLibrary(tmp_path / "lib.json")
    series = SeriesLibrary(tmp_path / "series.json")
    return TestClient(create_app(FakeCtx(), library=movies, series_library=series)), series


def test_series_add_persists(tmp_path):
    client, series = _client(tmp_path)
    resp = client.post("/series/add", data={"tmdb_id": "1399", "title": "GoT", "year": "2011", "poster_path": "/g.jpg"})
    assert resp.status_code == 200
    assert [s.tmdb_id for s in series.list()] == [1399]


def test_library_shows_series_section_with_episode_count(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1, title="My Show", year="2024", added_at=NOW,
                            grabbed=["S01E01", "S01E02"]))
    html = client.get("/library").text
    assert "My Show" in html
    assert "2 episodes" in html
    assert "Series" in html


def test_series_remove(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1, title="My Show", added_at=NOW))
    client.post("/series/1/remove")
    assert series.list() == []


def test_discover_series_card_has_follow_button(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover/search", params={"q": "got"}).text
    assert 'hx-post="/series/add"' in html
