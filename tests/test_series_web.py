from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import EpisodeInfo, MediaResult, SeasonInfo, WantedSeries
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 21, tzinfo=UTC)


class FakeTmdb:
    enabled = True

    async def search(self, query):
        return [
            MediaResult(tmdb_id=1399, media_type="tv", title="Game of Thrones", year="2011",
                        poster_path="/g.jpg"),
        ]

    async def get_details(self, media_type, tmdb_id):
        if tmdb_id == 1399:
            return MediaResult(
                tmdb_id=1399,
                media_type="tv",
                title="Game of Thrones",
                original_title="Game of Thrones",
                year="2011",
                overview="Winter is coming",
                poster_path="/g.jpg",
            )
        return None

    async def seasons(self, tv_id):
        if tv_id == 1399:
            return [
                SeasonInfo(
                    season_number=1,
                    name="Saison 1",
                    episode_count=2,
                    episodes=[
                        EpisodeInfo(season_number=1, episode_number=1, code="S01E01", name="L'hiver vient", air_date="2011-04-17"),
                        EpisodeInfo(season_number=1, episode_number=2, code="S01E02", name="La Route royale", air_date="2011-04-24"),
                    ],
                )
            ]
        return []


class _FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None, episodes=None):
        self._owned = owned or {}
        self._episodes = episodes or {}

    async def owned(self):
        return dict(self._owned)

    async def episodes(self, item_id):
        return set(self._episodes.get(item_id, set()))

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
    return TestClient(create_app(FakeCtx(jf=jf), library=movies, series_library=series)), series


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


def test_series_detail_modal_shows_seasons_and_episodes(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1399, title="Game of Thrones", year="2011", added_at=NOW))
    resp = client.get("/series/1399/detail", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    html = resp.text
    assert "Game of Thrones" in html
    assert "Saison 1" in html
    assert "S01E01" in html
    assert "L&#39;hiver vient" in html or "L'hiver vient" in html
    assert "S01E02" in html
    # Torrent search buttons
    assert "cat=tv" in html
    assert "Game+of+Thrones+S01E01" in html or "Game%20of%20Thrones%20S01E01" in html


def test_series_detail_shows_jellyfin_status(tmp_path):
    jf = _FakeJellyfin(owned={"tv:1399": "jf-got"}, episodes={"jf-got": {"S01E01"}})
    client, series = _client(tmp_path, jf=jf)
    series.add(WantedSeries(tmdb_id=1399, title="Game of Thrones", year="2011", added_at=NOW))
    resp = client.get("/series/1399/detail", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Dans Jellyfin" in resp.text


def test_series_detail_shows_grabbed_status(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1399, title="Game of Thrones", year="2011", added_at=NOW, grabbed=["S01E02"]))
    resp = client.get("/series/1399/detail", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Telecharge" in resp.text


def test_series_detail_full_page(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1399, title="Game of Thrones", year="2011", added_at=NOW))
    resp = client.get("/series/1399")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text
    assert "Game of Thrones" in resp.text


def test_series_detail_not_found_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/series/999999")
    assert resp.status_code == 404
