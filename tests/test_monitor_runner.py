from torsearch.config import Config, MonitorConfig, SavedSearch
from torsearch.models import Category, SearchResult
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import MonitorRunner, run_cycle, select_new
from torsearch.search.filters import ResultFilters


def _r(title, seeders=10, infohash=None, url=None):
    return SearchResult(title=title, size=1000, seeders=seeders, leechers=0, source="trk",
                        category=Category.MOVIES, download_url=url or ("magnet:?xt=urn:btih:" + title),
                        infohash=infohash)


class FakeSearch:
    def __init__(self, results, error=False):
        self._results = results
        self._error = error

    async def search(self, query, category):
        if self._error:
            raise RuntimeError("boom")
        return list(self._results)


class FakeTransmission:
    def __init__(self):
        self.added = []

    def add(self, url):
        self.added.append(url)
        return 1


def test_select_new_picks_best_unseen():
    res = [_r("low", seeders=5, infohash="A"), _r("high", seeders=50, infohash="B")]
    assert select_new(res, ResultFilters(), set()).title == "high"
    assert select_new(res, ResultFilters(), {"B"}).title == "low"
    assert select_new(res, ResultFilters(), {"A", "B"}) is None


async def test_run_cycle_auto_grabs_and_records(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    tr = FakeTransmission()
    created = await run_cycle(cfg, FakeSearch([_r("Best", seeders=99, infohash="X")]), tr, history)
    assert tr.added == ["magnet:?xt=urn:btih:Best"]
    assert [r.kind for r in created] == ["grabbed"]
    assert history.seen_keys("s") == {"X"}


async def test_run_cycle_notify_records_without_grab(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="notify")])
    tr = FakeTransmission()
    created = await run_cycle(cfg, FakeSearch([_r("Found", infohash="Y")]), tr, history)
    assert tr.added == []
    assert [r.kind for r in created] == ["found"]


async def test_run_cycle_skips_already_seen(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    search = FakeSearch([_r("Best", infohash="X")])
    await run_cycle(cfg, search, FakeTransmission(), history)
    assert await run_cycle(cfg, search, FakeTransmission(), history) == []


async def test_run_cycle_disabled_globally(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=False), saved_searches=[SavedSearch(name="s", query="q")])
    assert await run_cycle(cfg, FakeSearch([_r("X", infohash="Z")]), FakeTransmission(), history) == []


async def test_run_cycle_disabled_search_ignored(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="off", query="q", enabled=False)])
    assert await run_cycle(cfg, FakeSearch([_r("X", infohash="Z")]), FakeTransmission(), history) == []


async def test_run_cycle_resilient_to_search_error(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True), saved_searches=[SavedSearch(name="s", query="q")])
    assert await run_cycle(cfg, FakeSearch([], error=True), FakeTransmission(), history) == []


async def test_runner_start_and_stop(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")

    class Ctx:
        config = Config(monitor=MonitorConfig(enabled=False))
        search_service = FakeSearch([])
        transmission = FakeTransmission()

    runner = MonitorRunner(Ctx(), history)
    await runner.start()
    assert runner._task is not None
    await runner.stop()
    assert runner._task is None


class FakeNotifier:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    async def notify(self, channels, record):
        self.calls.append((channels, record))
        if self._fail:
            raise RuntimeError("notif boom")


async def test_run_cycle_notifies_on_record(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="notify")])
    notifier = FakeNotifier()
    await run_cycle(cfg, FakeSearch([_r("Found", infohash="Y")]), FakeTransmission(), history, notifier)
    assert len(notifier.calls) == 1
    assert notifier.calls[0][1].title == "Found"


async def test_run_cycle_survives_notifier_error(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    created = await run_cycle(cfg, FakeSearch([_r("Best", infohash="X")]), FakeTransmission(), history, FakeNotifier(fail=True))
    assert [r.kind for r in created] == ["grabbed"]  # record created despite notif failure


from datetime import datetime, timezone

from torsearch.config import LibraryConfig
from torsearch.library.movies import MovieLibrary
from torsearch.models import WantedMovie
from torsearch.monitor.runner import run_movie_cycle

MNOW = datetime(2026, 6, 20, tzinfo=timezone.utc)


def _lib(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=MNOW))
    return lib


async def test_movie_cycle_grabs_and_marks(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    created = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="X")]), tr, history)
    assert tr.added == ["magnet:?xt=urn:btih:Dune.2024.1080p"]
    assert [r.kind for r in created] == ["grabbed"]
    assert lib.wanted() == []
    assert lib.list()[0].status == "grabbed"


async def test_movie_cycle_disabled_globally(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=False))
    out = await run_movie_cycle(cfg, _lib(tmp_path), FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_movie_cycle_respects_quality_profile(tmp_path):
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["2160p"], min_seeders=1))
    tr = FakeTransmission()
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="X")]),
                                tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []
    assert lib.wanted()


async def test_movie_cycle_skips_already_grabbed(tmp_path):
    lib = _lib(tmp_path)
    lib.mark_grabbed(1, "old", MNOW)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_movie_cycle_resilient_to_search_error(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=True))
    out = await run_movie_cycle(cfg, _lib(tmp_path), FakeSearch([], error=True),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedSeries
from torsearch.monitor.runner import run_series_cycle


def _slib(tmp_path, grabbed=None):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(WantedSeries(tmdb_id=1, title="Show", year="2024", added_at=MNOW,
                         grabbed=grabbed or []))
    return lib


async def test_series_cycle_grabs_multiple_new_episodes(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    created = await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.1080p", seeders=50, infohash="A"),
        _r("Show.S01E02.1080p", seeders=40, infohash="B"),
    ]), tr, history)
    assert len(tr.added) == 2
    assert [r.kind for r in created] == ["grabbed", "grabbed"]
    assert lib.list()[0].grabbed == ["S01E01", "S01E02"]


async def test_series_cycle_dedupes_same_episode(tmp_path):
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.2160p", seeders=80, infohash="A"),
        _r("Show.S01E01.1080p", seeders=50, infohash="B"),
    ]), tr, MonitorHistory(tmp_path / "m.json"))
    assert len(tr.added) == 1


async def test_series_cycle_skips_already_grabbed(tmp_path):
    lib = _slib(tmp_path, grabbed=["S01E01"])
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                                 tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []


async def test_series_cycle_disabled_globally(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=False))
    out = await run_series_cycle(cfg, _slib(tmp_path), FakeSearch([_r("Show.S01E01", infohash="A")]),
                                 FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_series_cycle_respects_quality_profile(tmp_path):
    from torsearch.config import LibraryConfig
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["2160p"]))
    tr = FakeTransmission()
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", seeders=50, infohash="A")]),
                                 tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []
