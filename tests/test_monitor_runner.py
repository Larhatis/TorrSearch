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
        self.dirs = []

    def add(self, url, download_dir=None):
        self.added.append(url)
        self.dirs.append(download_dir)
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


from datetime import UTC, datetime

from torsearch.config import LibraryConfig
from torsearch.library.movies import MovieLibrary
from torsearch.models import WantedMovie
from torsearch.monitor.runner import run_movie_cycle

MNOW = datetime(2026, 6, 20, tzinfo=UTC)


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


async def test_movie_cycle_uses_movies_path(tmp_path):
    from torsearch.config import PathsConfig
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), paths=PathsConfig(by_category={"movies": "/data/films"}))
    tr = FakeTransmission()
    await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                          tr, MonitorHistory(tmp_path / "m.json"))
    assert tr.dirs == ["/data/films"]


async def test_series_cycle_uses_tv_path(tmp_path):
    from torsearch.config import PathsConfig
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), paths=PathsConfig(by_category={"tv": "/data/series"}))
    tr = FakeTransmission()
    await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                           tr, MonitorHistory(tmp_path / "m.json"))
    assert tr.dirs == ["/data/series"]


# --- Feature 1: Jellyfin auto-refresh on download completion ---

class _Torrent:
    def __init__(self, tid, percent):
        self.id = tid
        self.percent = percent


class FakeTransmissionList:
    def __init__(self, torrents, error=False):
        self._torrents = torrents
        self._error = error

    def list_torrents(self):
        if self._error:
            raise RuntimeError("boom")
        return list(self._torrents)


class FakeJellyfin:
    def __init__(self, enabled=True, owned=None, episodes=None):
        self.enabled = enabled
        self._owned = owned or {}
        self._episodes = episodes or {}
        self.refresh_calls = 0
        self.owned_calls = 0

    async def refresh(self):
        self.refresh_calls += 1
        return True

    async def owned(self):
        self.owned_calls += 1
        return dict(self._owned)

    async def episodes(self, item_id):
        return set(self._episodes.get(item_id, set()))


class FakeTmdb:
    def __init__(self, enabled=True, episodes=None):
        self.enabled = enabled
        self._episodes = episodes or {}

    async def episodes(self, tv_id):
        return set(self._episodes.get(tv_id, set()))


async def test_refresh_triggers_on_new_completion():
    from torsearch.monitor.runner import run_jellyfin_refresh
    jf = FakeJellyfin()
    tr = FakeTransmissionList([_Torrent(1, 100.0), _Torrent(2, 42.0)])
    seen = await run_jellyfin_refresh(tr, jf, set())
    assert jf.refresh_calls == 1
    assert seen == {1}


async def test_refresh_not_repeated_without_new_completion():
    from torsearch.monitor.runner import run_jellyfin_refresh
    jf = FakeJellyfin()
    tr = FakeTransmissionList([_Torrent(1, 100.0)])
    seen = await run_jellyfin_refresh(tr, jf, {1})
    assert jf.refresh_calls == 0
    assert seen == {1}


async def test_refresh_triggers_again_when_another_finishes():
    from torsearch.monitor.runner import run_jellyfin_refresh
    jf = FakeJellyfin()
    tr = FakeTransmissionList([_Torrent(1, 100.0), _Torrent(2, 100.0)])
    seen = await run_jellyfin_refresh(tr, jf, {1})
    assert jf.refresh_calls == 1
    assert seen == {1, 2}


async def test_refresh_skipped_when_jellyfin_disabled():
    from torsearch.monitor.runner import run_jellyfin_refresh
    jf = FakeJellyfin(enabled=False)
    tr = FakeTransmissionList([_Torrent(1, 100.0)])
    seen = await run_jellyfin_refresh(tr, jf, set())
    assert jf.refresh_calls == 0
    assert seen == set()


async def test_refresh_survives_transmission_error():
    from torsearch.monitor.runner import run_jellyfin_refresh
    jf = FakeJellyfin()
    tr = FakeTransmissionList([], error=True)
    seen = await run_jellyfin_refresh(tr, jf, {5})
    assert jf.refresh_calls == 0
    assert seen == {5}


async def test_refresh_noop_when_jellyfin_none():
    from torsearch.monitor.runner import run_jellyfin_refresh
    tr = FakeTransmissionList([_Torrent(1, 100.0)])
    seen = await run_jellyfin_refresh(tr, None, set())
    assert seen == set()


# --- Feature 2: targeted missing-episode series cycle ---

async def test_series_cycle_targets_only_missing_episodes(tmp_path):
    lib = _slib(tmp_path)  # tmdb_id=1, no grabbed
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"tv:1": "jf1"}, episodes={"jf1": {"S01E01"}})
    tmdb = FakeTmdb(episodes={1: {"S01E01", "S01E02", "S01E03"}})
    created = await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.1080p", seeders=50, infohash="A"),  # already in Jellyfin -> skip
        _r("Show.S01E02.1080p", seeders=40, infohash="B"),  # missing -> grab
        _r("Show.S01E03.1080p", seeders=30, infohash="C"),  # missing -> grab
        _r("Show.S01E04.1080p", seeders=20, infohash="D"),  # not aired -> skip
    ]), tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf, tmdb=tmdb)
    assert len(tr.added) == 2
    assert [r.title for r in created] == ["Show.S01E02.1080p", "Show.S01E03.1080p"]
    assert lib.list()[0].grabbed == ["S01E02", "S01E03"]


async def test_series_cycle_skips_complete_series(tmp_path):
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"tv:1": "jf1"}, episodes={"jf1": {"S01E01"}})
    tmdb = FakeTmdb(episodes={1: {"S01E01"}})  # everything aired is present
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                                 tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf, tmdb=tmdb)
    assert out == []
    assert tr.added == []


async def test_series_cycle_season_pack_covers_missing(tmp_path):
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={}, episodes={})  # nothing in Jellyfin
    tmdb = FakeTmdb(episodes={1: {"S02E01", "S02E02"}})
    await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S02.COMPLETE.1080p", seeders=60, infohash="P"),
    ]), tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf, tmdb=tmdb)
    assert len(tr.added) == 1
    assert lib.list()[0].grabbed == ["S02E01", "S02E02"]


async def test_series_cycle_prefers_smaller_torrent_for_small_gap(tmp_path):
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    # Only S02E05 is missing (E01-E04 already in Jellyfin).
    jf = FakeJellyfin(owned={"tv:1": "jf1"},
                      episodes={"jf1": {"S02E01", "S02E02", "S02E03", "S02E04"}})
    tmdb = FakeTmdb(episodes={1: {f"S02E0{n}" for n in range(1, 6)}})
    results = [
        SearchResult(title="Show.S02.COMPLETE.1080p", size=20_000_000_000, seeders=100,
                     leechers=0, source="t", category=Category.TV,
                     download_url="magnet:?P", infohash="P"),
        SearchResult(title="Show.S02E05.1080p", size=500_000_000, seeders=40,
                     leechers=0, source="t", category=Category.TV,
                     download_url="magnet:?S", infohash="S"),
    ]
    created = await run_series_cycle(cfg, lib, FakeSearch(results), tr,
                                     MonitorHistory(tmp_path / "m.json"), jellyfin=jf, tmdb=tmdb)
    assert [r.title for r in created] == ["Show.S02E05.1080p"]  # the single, not the 20 GB pack
    assert lib.list()[0].grabbed == ["S02E05"]


# --- Improvement 1: re-grab failed downloads after cooldown ---

from datetime import UTC, timedelta


def _grab_record(title, when, search="Show"):
    from torsearch.monitor.history import MonitorRecord
    return MonitorRecord(search=search, title=title, source="trk",
                         download_url="magnet:?" + title, kind="grabbed", at=when)


async def test_series_cycle_regrabs_failed_after_window(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    # Episode was grabbed 3 days ago but never landed in Jellyfin.
    now = datetime.now(UTC)
    history.add(_grab_record("Show.S01E02.1080p", now - timedelta(hours=72)))
    lib = _slib(tmp_path, grabbed=["S01E02"])
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"tv:1": "jf1"}, episodes={"jf1": set()})  # absent from Jellyfin
    tmdb = FakeTmdb(episodes={1: {"S01E01", "S01E02"}})
    created = await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.1080p", seeders=50, infohash="A"),
        _r("Show.S01E02.1080p", seeders=40, infohash="B"),
    ]), tr, history, jellyfin=jf, tmdb=tmdb)
    titles = {r.title for r in created}
    assert "Show.S01E02.1080p" in titles  # re-grabbed despite being in series.grabbed
    assert len(tr.added) == 2


async def test_series_cycle_keeps_recent_grab_in_cooldown(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    now = datetime.now(UTC)
    history.add(_grab_record("Show.S01E02.1080p", now - timedelta(hours=1)))  # still downloading
    lib = _slib(tmp_path, grabbed=["S01E02"])
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"tv:1": "jf1"}, episodes={"jf1": set()})
    tmdb = FakeTmdb(episodes={1: {"S01E01", "S01E02"}})
    created = await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.1080p", seeders=50, infohash="A"),
        _r("Show.S01E02.1080p", seeders=40, infohash="B"),
    ]), tr, history, jellyfin=jf, tmdb=tmdb)
    assert [r.title for r in created] == ["Show.S01E01.1080p"]  # E02 still in cooldown
    assert len(tr.added) == 1


async def test_series_cycle_legacy_grabbed_not_regrabbed(tmp_path):
    # grabbed before this feature: present in series.grabbed but no history record.
    history = MonitorHistory(tmp_path / "m.json")
    lib = _slib(tmp_path, grabbed=["S01E01"])
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"tv:1": "jf1"}, episodes={"jf1": set()})  # absent, but no history
    tmdb = FakeTmdb(episodes={1: {"S01E01"}})
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                                 tr, history, jellyfin=jf, tmdb=tmdb)
    assert out == []  # legacy grab kept, no re-grab storm
    assert tr.added == []


# --- Improvement 3: fetch Jellyfin owned() once per cycle ---

async def test_series_cycle_fetches_owned_once(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(WantedSeries(tmdb_id=1, title="ShowA", year="2024", added_at=MNOW))
    lib.add(WantedSeries(tmdb_id=2, title="ShowB", year="2024", added_at=MNOW))
    cfg = Config(monitor=MonitorConfig(enabled=True))
    jf = FakeJellyfin(owned={}, episodes={})
    tmdb = FakeTmdb(episodes={})
    await run_series_cycle(cfg, lib, FakeSearch([]), FakeTransmission(),
                           MonitorHistory(tmp_path / "m.json"), jellyfin=jf, tmdb=tmdb)
    assert jf.owned_calls == 1


# --- Improvement A: re-grab failed movie downloads (Jellyfin as truth) ---

async def test_movie_cycle_regrabs_failed_after_window(tmp_path):
    lib = _lib(tmp_path)
    now = datetime.now(UTC)
    lib.mark_grabbed(1, "Dune.2024.old", now - timedelta(hours=72))  # grabbed long ago
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={})  # not present in Jellyfin -> failed download
    created = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="X")]),
                                    tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf)
    assert len(tr.added) == 1
    assert [r.kind for r in created] == ["grabbed"]


async def test_movie_cycle_present_in_jellyfin_not_regrabbed(tmp_path):
    lib = _lib(tmp_path)
    now = datetime.now(UTC)
    lib.mark_grabbed(1, "Dune.2024.old", now - timedelta(hours=72))
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={"movie:1": "jf1"})  # confirmed present
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf)
    assert out == []
    assert tr.added == []


async def test_movie_cycle_recent_grab_in_cooldown(tmp_path):
    lib = _lib(tmp_path)
    now = datetime.now(UTC)
    lib.mark_grabbed(1, "Dune.2024.old", now - timedelta(hours=1))  # still downloading
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    jf = FakeJellyfin(owned={})
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                tr, MonitorHistory(tmp_path / "m.json"), jellyfin=jf)
    assert out == []
    assert tr.added == []


async def test_movie_cycle_jellyfin_disabled_keeps_grabbed(tmp_path):
    lib = _lib(tmp_path)
    now = datetime.now(UTC)
    lib.mark_grabbed(1, "Dune.2024.old", now - timedelta(hours=72))
    cfg = Config(monitor=MonitorConfig(enabled=True, regrab_hours=48))
    tr = FakeTransmission()
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                tr, MonitorHistory(tmp_path / "m.json"), jellyfin=None)
    assert out == []
    assert tr.added == []


# --- Improvement R2: quality upgrades (movies, opt-in) ---

async def test_movie_cycle_upgrades_quality_when_enabled(tmp_path):
    lib = _lib(tmp_path)
    lib.mark_grabbed(1, "Dune.2024.720p", MNOW)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(upgrades=True))
    tr = FakeTransmission()
    created = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="U")]),
                                    tr, MonitorHistory(tmp_path / "m.json"))
    assert [r.title for r in created] == ["Dune.2024.1080p"]
    assert lib.list()[0].grabbed_title == "Dune.2024.1080p"


async def test_movie_cycle_no_upgrade_when_disabled(tmp_path):
    lib = _lib(tmp_path)
    lib.mark_grabbed(1, "Dune.2024.720p", MNOW)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(upgrades=False))
    tr = FakeTransmission()
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="U")]),
                                tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert lib.list()[0].grabbed_title == "Dune.2024.720p"


async def test_movie_cycle_no_upgrade_when_not_better(tmp_path):
    lib = _lib(tmp_path)
    lib.mark_grabbed(1, "Dune.2024.1080p", MNOW)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(upgrades=True))
    tr = FakeTransmission()
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="U")]),
                                tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []
