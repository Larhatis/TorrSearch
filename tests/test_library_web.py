import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedMovie
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)


class FakeTmdb:
    enabled = True

    async def search(self, query):
        return [MediaResult(tmdb_id=693134, media_type="movie", title="Dune", year="2024",
                            poster_path="/a.jpg")]


class _FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)


class FakeCtx:
    def __init__(self, monitor_on=False):
        self.tmdb = FakeTmdb()
        self.config = Config(monitor=MonitorConfig(enabled=monitor_on))
        self.jellyfin = _FakeJellyfin()


def _client(tmp_path, monitor_on=False):
    lib = MovieLibrary(tmp_path / "lib.json")
    series = SeriesLibrary(tmp_path / "series.json")
    return TestClient(create_app(FakeCtx(monitor_on), library=lib, series_library=series)), lib


def test_library_add_persists(tmp_path):
    client, lib = _client(tmp_path)
    resp = client.post("/library/add", data={"tmdb_id": "693134", "title": "Dune", "year": "2024", "poster_path": "/a.jpg"})
    assert resp.status_code == 200
    assert [m.tmdb_id for m in lib.list()] == [693134]


def test_library_page_lists_movies_with_status(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=NOW))
    html = client.get("/library").text
    assert "Dune" in html
    assert "Voulu" in html


def test_library_page_warns_when_monitor_off(tmp_path):
    client, _ = _client(tmp_path, monitor_on=False)
    assert "surveillance" in client.get("/library").text.lower()


def test_library_remove(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=1, title="Dune", added_at=NOW))
    client.post("/library/1/remove")
    assert lib.list() == []


def test_library_marks_owned_movie(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=693134, title="Dune", year="2024", added_at=NOW))
    client.app.state.ctx.jellyfin = _FakeJellyfin(owned={"movie:693134": "it-1"})
    html = client.get("/library").text
    assert "Dans Jellyfin" in html
    assert "it-1" in html


def test_discover_movie_card_has_add_button(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover/search", params={"q": "dune"}).text
    assert 'hx-post="/library/add"' in html


def test_nav_marks_library_active(tmp_path):
    client, _ = _client(tmp_path)
    assert re.search(r'href="/library"[^>]*aria-current="page"', client.get("/library").text)


def test_update_library_profile(tmp_path):
    from torsearch.context import AppContext
    from torsearch.settings.store import SettingsStore

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx, library=MovieLibrary(tmp_path / "lib.json")))
    resp = client.post("/settings/library", data={"quality": ["1080p"], "min_seeders": "5"})
    assert resp.status_code == 200
    assert ctx.config.library.qualities == ["1080p"]
    assert ctx.config.library.min_seeders == 5
