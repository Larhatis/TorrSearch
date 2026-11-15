"""No automatic send onto a nearly full disk (chantier 13)."""

from datetime import UTC, datetime

from torsearch.config import Config, LibraryConfig, MonitorConfig, PathsConfig, SavedSearch
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import run_cycle, run_movie_cycle, run_series_cycle

GB = 1_000_000_000
NOW = datetime(2026, 6, 20, tzinfo=UTC)


def _r(title, size=10 * GB, infohash="H"):
    return SearchResult(title=title, size=size, seeders=50, leechers=0, source="trk",
                        category=Category.MOVIES, download_url="magnet:?xt=urn:btih:" + title,
                        infohash=infohash)


class Search:
    def __init__(self, results):
        self._results = results

    async def search(self, query, category):
        return list(self._results)


class SpaceTransmission:
    """Async fake answering ``free_space`` with the same value for every folder."""

    def __init__(self, free):
        self.free = free
        self.added = []
        self.measured = []

    async def free_space(self, path):
        self.measured.append(path)
        return self.free

    async def add(self, url, download_dir=None):
        self.added.append((url, download_dir))
        return 1

    async def list_torrents(self):
        return []


def _cfg(**library):
    return Config(monitor=MonitorConfig(enabled=True),
                  paths=PathsConfig(by_category={"movies": "/d/disk1/Films", "tv": "/d/disk2"}),
                  library=LibraryConfig(**library),
                  saved_searches=[SavedSearch(name="s", query="q", mode="auto")])


def _movies(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=NOW))
    return lib


def _series(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(WantedSeries(tmdb_id=1, title="Show", year="2024", added_at=NOW))
    return lib


async def test_movie_not_sent_when_disk_nearly_full(tmp_path):
    lib, history = _movies(tmp_path), MonitorHistory(tmp_path / "m.json")
    tr = SpaceTransmission(free=55 * GB)  # 55 - 10 < 50
    created = await run_movie_cycle(_cfg(), lib, Search([_r("Dune.2024.1080p")]), tr, history)
    assert created == [] and tr.added == []
    assert history.records() == []
    assert lib.wanted()  # still wanted: retried at its next search
    assert tr.measured == ["/d/disk1/Films/Dune (2024) [tmdbid-1]"]


async def test_movie_sent_when_there_is_room(tmp_path):
    lib = _movies(tmp_path)
    tr = SpaceTransmission(free=600 * GB)
    created = await run_movie_cycle(_cfg(), lib, Search([_r("Dune.2024.1080p")]), tr,
                                    MonitorHistory(tmp_path / "m.json"))
    assert [r.kind for r in created] == ["grabbed"] and len(tr.added) == 1


async def test_threshold_zero_sends_even_on_a_full_disk(tmp_path):
    tr = SpaceTransmission(free=1 * GB)
    await run_movie_cycle(_cfg(min_free_gb=0), _movies(tmp_path), Search([_r("Dune.2024.1080p")]), tr,
                          MonitorHistory(tmp_path / "m.json"))
    assert len(tr.added) == 1


async def test_episode_not_sent_nor_marked_when_disk_nearly_full(tmp_path):
    lib, history = _series(tmp_path), MonitorHistory(tmp_path / "m.json")
    tr = SpaceTransmission(free=55 * GB)
    created = await run_series_cycle(_cfg(), lib, Search([_r("Show.S01E01.1080p")]), tr, history)
    assert created == [] and tr.added == []
    assert lib.list()[0].grabbed == []
    assert history.records() == []


async def test_free_search_not_sent_when_disk_nearly_full(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    tr = SpaceTransmission(free=55 * GB)
    created = await run_cycle(_cfg(), Search([_r("Some.Release.1080p", infohash="X")]), tr, history)
    assert created == [] and tr.added == []
    assert history.seen_keys("s") == set()  # not seen: tried again once there is room


class MsgNotifier:
    def __init__(self):
        self.messages = []

    async def notify(self, channels, record):
        pass

    async def notify_message(self, channels, title, body):
        self.messages.append((title, body))


async def test_runner_warns_once_a_day_when_a_disk_is_nearly_full(tmp_path):
    from torsearch.monitor.runner import MonitorRunner

    class Ctx:
        config = Config(monitor=MonitorConfig(enabled=True),
                        paths=PathsConfig(by_category={"movies": "/d/disk1/Films", "tv": "/d/disk2"}))
        search_service = Search([])
        transmission = SpaceTransmission(free=40 * GB)

    notifier = MsgNotifier()
    runner = MonitorRunner(Ctx(), MonitorHistory(tmp_path / "m.json"), notifier=notifier)
    await runner.run_once()
    await runner.run_once()
    assert len(notifier.messages) == 1
    title, body = notifier.messages[0]
    assert title == "TorrSearch - disque presque plein"
    assert "Films : 40 Go libres" in body and "Series : 40 Go libres" in body and "50 Go" in body
    assert "Verifier maintenant" in body
    # Already told today: the next cycles do not even measure the disks again.
    measured = len(Ctx.transmission.measured)
    await runner.run_once()
    assert len(Ctx.transmission.measured) == measured


async def test_runner_no_disk_warning_when_surveillance_is_off(tmp_path):
    from torsearch.monitor.runner import MonitorRunner

    class Ctx:
        config = Config(monitor=MonitorConfig(enabled=False),
                        paths=PathsConfig(by_category={"movies": "/d/disk1/Films", "tv": "/d/disk2"}))
        search_service = Search([])
        transmission = SpaceTransmission(free=40 * GB)

    notifier = MsgNotifier()
    await MonitorRunner(Ctx(), MonitorHistory(tmp_path / "m.json"), notifier=notifier).run_once()
    assert notifier.messages == []


async def test_runner_silent_when_disks_have_room(tmp_path):
    from torsearch.monitor.runner import MonitorRunner

    class Ctx:
        config = Config(monitor=MonitorConfig(enabled=True),
                        paths=PathsConfig(by_category={"movies": "/d/disk1/Films", "tv": "/d/disk2"}))
        search_service = Search([])
        transmission = SpaceTransmission(free=600 * GB)

    notifier = MsgNotifier()
    await MonitorRunner(Ctx(), MonitorHistory(tmp_path / "m.json"), notifier=notifier).run_once()
    assert notifier.messages == []


async def test_series_does_not_send_more_than_the_disk_can_take(tmp_path):
    # Two 40 GB releases on 120 GB free with a 50 GB margin: only one fits (Transmission does
    # not reserve space on add, so measuring again before the second one would let it through).
    lib, history = _series(tmp_path), MonitorHistory(tmp_path / "m.json")
    tr = SpaceTransmission(free=120 * GB)
    await run_series_cycle(_cfg(), lib, Search([
        _r("Show.S01E01.2160p.REMUX", size=40 * GB, infohash="A"),
        _r("Show.S01E02.2160p.REMUX", size=40 * GB, infohash="B"),
    ]), tr, history)
    assert len(tr.added) == 1
