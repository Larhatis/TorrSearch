from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, SavedSearch
from torsearch.context import AppContext
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory, MonitorRecord
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None, history=None, library=None, series_library=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    history = history if history is not None else MonitorHistory(tmp_path / "monitor.json")
    return TestClient(create_app(ctx, history=history, library=library, series_library=series_library)), ctx, history


def test_surveillance_page_renders(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/surveillance")
    assert resp.status_code == 200
    assert "Surveillance" in resp.text
    assert 'name="interval_minutes"' in resp.text


def test_add_saved_search(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/searches", data={"name": "MaSerie", "query": "ma serie", "cat": "tv", "mode": "notify"})
    assert resp.status_code == 200
    assert "MaSerie" in resp.text
    assert [s.name for s in ctx.config.saved_searches] == ["MaSerie"]
    assert ctx.config.saved_searches[0].mode == "notify"


def test_add_duplicate_shows_error(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/surveillance/searches", data={"name": "s", "query": "q2"})
    assert "existe" in resp.text
    assert len(ctx.config.saved_searches) == 1


def test_toggle_and_delete_saved_search(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/surveillance/searches/s/toggle")
    assert ctx.config.saved_searches[0].enabled is False
    client.post("/surveillance/searches/s/delete")
    assert ctx.config.saved_searches == []


def test_update_monitor_settings(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "15"})
    assert resp.status_code == 200
    assert ctx.config.monitor.enabled is True
    assert ctx.config.monitor.interval_minutes == 15


def test_history_found_item_has_send_button(tmp_path):
    history = MonitorHistory(tmp_path / "monitor.json")
    history.add(MonitorRecord(search="s", title="Found.It", source="trk", infohash="H",
                              download_url="magnet:?xt=urn:btih:H", kind="found",
                              at=datetime(2024, 1, 1, tzinfo=UTC)))
    client, _, _ = _client(tmp_path, history=history)
    resp = client.get("/surveillance")
    assert "Found.It" in resp.text
    assert "Envoyer" in resp.text


def test_update_monitor_preserves_regrab_hours(tmp_path):
    from torsearch.config import MonitorConfig

    client, ctx, _ = _client(tmp_path, Config(monitor=MonitorConfig(regrab_hours=72)))
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "15"})
    assert resp.status_code == 200
    assert ctx.config.monitor.regrab_hours == 72
    assert ctx.config.monitor.interval_minutes == 15


def test_update_monitor_rejects_an_interval_below_one_minute(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "0"})
    assert "Erreur" in resp.text
    assert ctx.config.monitor.interval_minutes == 30
    assert ctx.config.monitor.enabled is False


def test_run_now_warns_when_disabled(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.post("/surveillance/run-now")
    assert resp.status_code == 200
    assert "Active" in resp.text and "la surveillance" in resp.text


def test_run_now_triggers_when_enabled(tmp_path):
    from torsearch.config import MonitorConfig

    class FakeRunner:
        def __init__(self):
            self.ran = False

        async def run_once(self):
            self.ran = True
            return []

    store = SettingsStore(tmp_path / "settings.json")
    store.save(Config(monitor=MonitorConfig(enabled=True)))
    ctx = AppContext(store)
    history = MonitorHistory(tmp_path / "monitor.json")
    runner = FakeRunner()
    app = create_app(ctx, history=history, monitor=runner)
    client = TestClient(app)

    resp = client.post("/surveillance/run-now")
    assert resp.status_code == 200
    assert "Verification effectuee" in resp.text
    assert runner.ran is True


def test_clear_history(tmp_path):
    history = MonitorHistory(tmp_path / "monitor.json")
    history.add(MonitorRecord(search="Paolo", title="Paolo.S01E01", source="trk", download_url="http://x", kind="grabbed", at=datetime.now(UTC)))
    assert len(history.records()) == 1

    client, _, _ = _client(tmp_path, history=history)
    # The surveillance page shows clear history button when records exist
    resp = client.get("/surveillance")
    assert "Vider l&#39;historique" in resp.text or "Vider l'historique" in resp.text

    # Clear history
    resp = client.post("/surveillance/history/clear")
    assert resp.status_code == 200
    assert "Historique vide." in resp.text
    assert len(history.records()) == 0


def test_surveillance_history_route(tmp_path):
    history = MonitorHistory(tmp_path / "monitor.json")
    history.add(MonitorRecord(search="Paolo", title="Paolo.S01E01", source="trk", download_url="http://x", kind="grabbed", at=datetime.now(UTC)))
    client, _, _ = _client(tmp_path, history=history)

    resp = client.get("/surveillance/history")
    assert resp.status_code == 200
    assert "Paolo.S01E01" in resp.text


def test_quick_add_saved_search(tmp_path):
    client, ctx, _ = _client(tmp_path)
    assert ctx.config.monitor.enabled is False
    resp = client.post("/surveillance/quick-add", data={"query": "Avatar 3", "cat": "movies"})
    assert resp.status_code == 200
    assert "En surveillance (auto-download)" in resp.text
    assert "Avatar 3" in resp.text
    assert [s.name for s in ctx.config.saved_searches] == ["Avatar 3"]
    assert ctx.config.saved_searches[0].mode == "auto"
    assert ctx.config.saved_searches[0].category == Category.MOVIES
    assert ctx.config.saved_searches[0].exclude == ["cam", "ts"]
    assert ctx.config.monitor.enabled is True


def test_quick_add_duplicate(tmp_path):
    client, ctx, _ = _client(tmp_path)
    client.post("/surveillance/quick-add", data={"query": "Avatar 3", "cat": "movies"})
    resp = client.post("/surveillance/quick-add", data={"query": "Avatar 3", "cat": "movies"})
    assert resp.status_code == 200
    assert "Deja en surveillance" in resp.text
    assert len(ctx.config.saved_searches) == 1


def test_quick_add_wakes_runner(tmp_path):
    class FakeRunner:
        def __init__(self):
            self.woken = False

        def wake(self):
            self.woken = True

    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    history = MonitorHistory(tmp_path / "monitor.json")
    runner = FakeRunner()
    app = create_app(ctx, history=history, monitor=runner)
    client = TestClient(app)

    resp = client.post("/surveillance/quick-add", data={"query": "Inception 2", "cat": "movies"})
    assert resp.status_code == 200
    assert runner.woken is True


def test_surveillance_page_displays_monitored_movies_and_series(tmp_path):
    lib = MovieLibrary(tmp_path / "movies.json")
    series_lib = SeriesLibrary(tmp_path / "series.json")
    now = datetime(2026, 1, 1, tzinfo=UTC)

    lib.add(WantedMovie(
        tmdb_id=101, title="Dune Deux", year="2024", poster_path="/dune.jpg",
        status="wanted", added_at=now,
    ))
    lib.add(WantedMovie(
        tmdb_id=102, title="Avatar 2", year="2022", poster_path="/avatar.jpg",
        status="grabbed", added_at=now, grabbed_title="Avatar.2022.MULTi.1080p",
    ))
    series_lib.add(WantedSeries(
        tmdb_id=201, title="Lanterns", year="2026", poster_path="/lanterns.jpg",
        added_at=now, grabbed=["S01E01", "S01E02"],
    ))

    client, _, _ = _client(tmp_path, library=lib, series_library=series_lib)
    resp = client.get("/surveillance")
    assert resp.status_code == 200
    # Movies & series titles
    assert "Dune Deux" in resp.text
    assert "Avatar 2" in resp.text
    assert "Lanterns" in resp.text
    # Posters
    assert "https://image.tmdb.org/t/p/w342/dune.jpg" in resp.text
    assert "https://image.tmdb.org/t/p/w342/lanterns.jpg" in resp.text
    # Status badges
    assert "En attente" in resp.text
    assert "Telecharge" in resp.text
    assert "Avatar.2022.MULTi.1080p" in resp.text
    assert "2 episodes" in resp.text


def test_surveillance_remove_movie_and_series(tmp_path):
    lib = MovieLibrary(tmp_path / "movies.json")
    series_lib = SeriesLibrary(tmp_path / "series.json")
    now = datetime(2026, 1, 1, tzinfo=UTC)

    lib.add(WantedMovie(tmdb_id=101, title="Dune", added_at=now))
    series_lib.add(WantedSeries(tmdb_id=201, title="Severance", added_at=now))

    client, _, _ = _client(tmp_path, library=lib, series_library=series_lib)
    resp = client.post("/surveillance/movies/101/remove")
    assert resp.status_code == 200
    assert lib.list() == []
    assert "Film retire de la surveillance." in resp.text

    resp2 = client.post("/surveillance/series/201/remove")
    assert resp2.status_code == 200
    assert series_lib.list() == []
    assert "Serie retiree de la surveillance." in resp2.text


def test_surveillance_regrab_movie(tmp_path):
    lib = MovieLibrary(tmp_path / "movies.json")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    lib.add(WantedMovie(
        tmdb_id=101, title="Dune", added_at=now,
        status="grabbed", grabbed_title="Dune.720p",
    ))

    client, _, _ = _client(tmp_path, library=lib)
    resp = client.post("/surveillance/movies/101/regrab")
    assert resp.status_code == 200
    movie = lib.get(101)
    assert movie is not None
    assert movie.status == "wanted"
    assert movie.grabbed_title is None
    assert "Film remis en recherche active." in resp.text




