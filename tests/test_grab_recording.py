"""Every send to Transmission lands in the grab registry, with who chose it (chantier 10)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig, SavedSearch
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.monitor.grabs import GrabRegistry
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import MonitorRunner, run_cycle, run_movie_cycle, run_series_cycle
from torsearch.search.service import SearchService
from torsearch.transmission.client import AddedTorrent
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 20, tzinfo=UTC)
ON = Config(monitor=MonitorConfig(enabled=True), saved_searches=[SavedSearch(name="s", query="best", mode="auto")])


def _r(title, infohash=None):
    return SearchResult(title=title, size=1000, seeders=50, leechers=0, source="trk", category=Category.MOVIES,
                        download_url="magnet:?xt=urn:btih:" + title, infohash=infohash)


class FakeSearch:
    def __init__(self, results):
        self._results = results

    async def search(self, query, category, only=None):
        return list(self._results)


class FakeTransmission:
    """``answer`` is what add() returns: an AddedTorrent, or a bare id like old fakes."""

    def __init__(self, answer):
        self._answer = answer
        self.added: list[str] = []

    async def add(self, url, download_dir=None):
        self.added.append(url)
        return self._answer

    async def list_torrents(self):
        return []


async def test_run_cycle_records_auto_grab_with_transmission_hash(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    tr = FakeTransmission(AddedTorrent(id=1, info_hash="tthash"))
    await run_cycle(ON, FakeSearch([_r("Best.2024.1080p", infohash="X")]), tr,
                    MonitorHistory(tmp_path / "m.json"), grabs=g)
    record = g.get("tthash")
    assert record.origin == "auto"
    assert record.target == "saved:s"


async def test_run_cycle_falls_back_to_tracker_hash(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    await run_cycle(ON, FakeSearch([_r("Best.2024.1080p", infohash="X")]), FakeTransmission(1),
                    MonitorHistory(tmp_path / "m.json"), grabs=g)
    assert g.is_auto("x")


async def test_grab_without_any_hash_records_nothing(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    tr = FakeTransmission(AddedTorrent(id=1, info_hash=""))
    await run_cycle(ON, FakeSearch([_r("Best.2024.1080p")]), tr, MonitorHistory(tmp_path / "m.json"), grabs=g)
    assert tr.added  # the grab itself happened
    assert g._c.count() == 0


async def test_history_keeps_tracker_infohash(tmp_path):
    # Copying Transmission's hash into the history would break its anti-duplicate key
    # (infohash or download_url, computed the same way on tracker results).
    history = MonitorHistory(tmp_path / "m.json")
    tr = FakeTransmission(AddedTorrent(id=1, info_hash="tthash"))
    await run_cycle(ON, FakeSearch([_r("Best.2024.1080p")]), tr, history, grabs=GrabRegistry(tmp_path / "g.db"))
    assert history.seen_keys("s") == {"magnet:?xt=urn:btih:Best.2024.1080p"}


async def test_movie_grab_is_recorded_auto(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=NOW))
    tr = FakeTransmission(AddedTorrent(id=1, info_hash="mh"))
    await run_movie_cycle(ON, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]), tr,
                          MonitorHistory(tmp_path / "m.json"), grabs=g)
    assert g.get("mh").origin == "auto"
    assert g.get("mh").target == "movie:1"


async def test_series_grab_is_recorded_auto(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(WantedSeries(tmdb_id=7, title="Show", year="2024", added_at=NOW))
    tr = FakeTransmission(AddedTorrent(id=1, info_hash="sh"))
    await run_series_cycle(ON, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]), tr,
                           MonitorHistory(tmp_path / "m.json"), grabs=g)
    assert g.get("sh").origin == "auto"
    assert g.get("sh").target == "tv:7"


async def test_monitor_runner_passes_the_registry_to_the_cycles(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")

    class Ctx:
        config = ON
        search_service = FakeSearch([_r("Best.2024.1080p", infohash="X")])
        transmission = FakeTransmission(AddedTorrent(id=1, info_hash="rh"))

    await MonitorRunner(Ctx(), MonitorHistory(tmp_path / "m.json"), grabs=g).run_once()
    assert g.is_auto("rh")


def test_manual_download_is_recorded_manual(tmp_path):
    class Ctx:
        search_service = SearchService([])
        transmission = FakeTransmission(AddedTorrent(id=7, info_hash="mm"))
        config = Config()
        jellyfin = None
        tmdb = None

    g = GrabRegistry(tmp_path / "g.db")
    client = TestClient(create_app(Ctx(), grabs=g))
    resp = client.post("/download", data={"download_url": "magnet:?x", "category": "movies",
                                          "title": "Some.Film.2020.1080p"})
    assert "Ajoute a Transmission" in resp.text
    assert g.get("mm").origin == "manual"
    assert g.get("mm").title == "Some.Film.2020.1080p"
