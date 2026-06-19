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
