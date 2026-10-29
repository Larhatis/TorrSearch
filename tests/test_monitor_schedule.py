from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from torsearch.config import Config, LibraryConfig, MonitorConfig, SavedSearch
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import run_cycle, run_movie_cycle, run_series_cycle
from torsearch.monitor.schedule import (
    SAVED_SEARCH_INTERVAL,
    SearchSchedule,
    movie_interval,
    series_interval,
)
from torsearch.search.matcher import matches_query

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _res(title: str, category: Category = Category.MOVIES) -> SearchResult:
    return SearchResult(
        title=title, size=1_000_000_000, seeders=10, leechers=1, source="t1",
        category=category, download_url=f"magnet:?xt=urn:btih:{title}", infohash=f"hash-{title}",
    )


class FakeSearch:
    def __init__(self, canned=None):
        self.canned = canned or {}
        self.searched: list[str] = []

    async def search(self, query, category=Category.ALL):
        self.searched.append(query)
        return list(self.canned.get(query, []))


class FakeTransmission:
    def __init__(self):
        self.added: list[str] = []

    async def add(self, url, download_dir=None):
        self.added.append(url)


class FakeTmdb:
    enabled = True

    def __init__(self, dates):
        self._dates = dates

    async def air_dates(self, tv_id):
        return dict(self._dates)


# --- schedule -------------------------------------------------------------------------

def test_schedule_due_when_never_searched(tmp_path):
    schedule = SearchSchedule(Database(tmp_path / "db.sqlite").collection("search_schedule"))
    assert schedule.is_due("movie:1", timedelta(hours=6), NOW)


def test_schedule_not_due_within_interval_and_persisted(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    SearchSchedule(db.collection("search_schedule")).mark("movie:1", NOW)
    schedule = SearchSchedule(db.collection("search_schedule"))  # reloaded from the DB
    assert not schedule.is_due("movie:1", timedelta(hours=6), NOW + timedelta(hours=5))
    assert schedule.is_due("movie:1", timedelta(hours=6), NOW + timedelta(hours=6))


def test_schedule_works_in_memory():
    schedule = SearchSchedule()
    schedule.mark("tv:1", NOW)
    assert not schedule.is_due("tv:1", timedelta(hours=1), NOW)


def test_movie_interval_short_for_new_movies():
    fresh = WantedMovie(tmdb_id=1, title="A", added_at=NOW - timedelta(days=2))
    old = WantedMovie(tmdb_id=2, title="B", added_at=NOW - timedelta(days=30))
    assert movie_interval(fresh, NOW) == timedelta(hours=6)
    assert movie_interval(old, NOW) == timedelta(hours=24)


def test_series_interval_follows_air_dates():
    today = date(2026, 10, 29)
    assert series_interval(["2026-10-28"], today) == timedelta(hours=1)
    assert series_interval(["2026-10-20"], today) == timedelta(hours=6)
    assert series_interval(["2025-01-01"], today) == timedelta(hours=24)
    assert series_interval(["2025-01-01", "2026-10-29"], today) == timedelta(hours=1)
    assert series_interval([None], today) == timedelta(hours=6)
    assert series_interval([], today) == timedelta(hours=6)


def test_matches_query_requires_every_word():
    assert matches_query("The.Last.of.Us.S02E03.MULTi.1080p", "last of us")
    assert not matches_query("The.Last.Kingdom.S01E01", "last of us")
    assert not matches_query("Anything", "")


# --- cycles with the RSS feed ---------------------------------------------------------

def _cfg(**kw):
    return Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["1080p"]), **kw)


async def test_movie_not_due_uses_feed_without_searching(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=NOW))
    schedule = SearchSchedule()
    schedule.mark("movie:1", datetime.now(UTC))
    search, tx = FakeSearch(), FakeTransmission()
    feed = [_res("Avatar.2009.MULTi.1080p.BluRay"), _res("Other.Movie.2020.1080p")]

    records = await run_movie_cycle(
        _cfg(), lib, search, tx, MonitorHistory(db), feed=feed, schedule=schedule,
    )
    assert search.searched == []
    assert [r.title for r in records] == ["Avatar.2009.MULTi.1080p.BluRay"]


async def test_movie_due_triggers_targeted_search_and_marks(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=NOW))
    schedule = SearchSchedule()
    search = FakeSearch({"Avatar 2009": [_res("Avatar.2009.MULTi.1080p.BluRay")]})

    await run_movie_cycle(
        _cfg(), lib, search, FakeTransmission(), MonitorHistory(db),
        feed=[_res("Unrelated.2020.1080p")], schedule=schedule,
    )
    assert search.searched == ["Avatar 2009"]
    assert schedule.last("movie:1") is not None


async def test_force_searches_even_when_not_due(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=NOW))
    schedule = SearchSchedule()
    schedule.mark("movie:1", datetime.now(UTC))
    search = FakeSearch()
    await run_movie_cycle(
        _cfg(), lib, search, FakeTransmission(), MonitorHistory(db),
        feed=[_res("Unrelated.2020.1080p")], schedule=schedule, force=True,
    )
    assert search.searched == ["Avatar 2009"]


async def test_empty_feed_falls_back_to_targeted_search(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=NOW))
    schedule = SearchSchedule()
    schedule.mark("movie:1", datetime.now(UTC))
    search = FakeSearch()
    await run_movie_cycle(
        _cfg(), lib, search, FakeTransmission(), MonitorHistory(db), feed=[], schedule=schedule,
    )
    assert search.searched == ["Avatar 2009"]


async def test_series_recent_gap_due_hourly(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = SeriesLibrary(db)
    lib.add(WantedSeries(tmdb_id=7, title="Severance", added_at=NOW, grabbed=["S01E01"]))
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tmdb = FakeTmdb({"S01E01": "2025-01-01", "S01E02": yesterday})
    schedule = SearchSchedule()
    schedule.mark("tv:7", datetime.now(UTC) - timedelta(minutes=90))
    search = FakeSearch({"Severance": [_res("Severance.S01E02.MULTi.1080p.WEB", Category.TV)]})
    tx = FakeTransmission()

    records = await run_series_cycle(
        _cfg(), lib, search, tx, MonitorHistory(db), tmdb=tmdb,
        feed=[_res("Unrelated.S01E01.1080p", Category.TV)], schedule=schedule,
    )
    assert search.searched == ["Severance"]  # last search 90 min ago > 1 h
    assert [r.title for r in records] == ["Severance.S01E02.MULTi.1080p.WEB"]


async def test_series_old_gap_not_due_uses_feed(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = SeriesLibrary(db)
    lib.add(WantedSeries(tmdb_id=7, title="Severance", added_at=NOW, grabbed=["S01E01"]))
    tmdb = FakeTmdb({"S01E01": "2025-01-01", "S01E02": "2025-01-08"})
    schedule = SearchSchedule()
    schedule.mark("tv:7", datetime.now(UTC) - timedelta(hours=3))
    search = FakeSearch()
    feed = [_res("Severance.S01E02.MULTi.1080p.WEB", Category.TV)]

    records = await run_series_cycle(
        _cfg(), lib, search, FakeTransmission(), MonitorHistory(db), tmdb=tmdb,
        feed=feed, schedule=schedule,
    )
    assert search.searched == []
    assert [r.title for r in records] == ["Severance.S01E02.MULTi.1080p.WEB"]


async def test_saved_search_not_due_matches_feed_by_words(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    cfg = _cfg(saved_searches=[SavedSearch(name="Dune", query="dune part two")])
    schedule = SearchSchedule()
    schedule.mark("saved:Dune", datetime.now(UTC))
    search = FakeSearch()
    feed = [_res("Dune.Part.Two.2024.MULTi.1080p"), _res("Dune.1984.1080p")]

    records = await run_cycle(cfg, search, FakeTransmission(), MonitorHistory(db),
                              feed=feed, schedule=schedule)
    assert search.searched == []
    assert [r.title for r in records] == ["Dune.Part.Two.2024.MULTi.1080p"]
    assert SAVED_SEARCH_INTERVAL == timedelta(hours=6)


class FeedSearch(FakeSearch):
    def __init__(self, feed):
        super().__init__()
        self.feed = feed
        self.recent_calls = 0

    async def recent(self, category=Category.ALL):
        self.recent_calls += 1
        return list(self.feed)


async def test_fetch_feed_skipped_when_nothing_watched(tmp_path):
    from torsearch.monitor.runner import fetch_feed

    search = FeedSearch([_res("A.2020.1080p")])
    lib = MovieLibrary(Database(tmp_path / "db.sqlite"))
    assert await fetch_feed(_cfg(), search, lib, None) is None
    assert search.recent_calls == 0
    lib.add(WantedMovie(tmdb_id=1, title="A", added_at=NOW))
    feed = await fetch_feed(_cfg(), search, lib, None)
    assert feed is not None and len(feed) == 1


async def test_fetch_feed_skipped_when_monitor_disabled(tmp_path):
    from torsearch.monitor.runner import fetch_feed

    search = FeedSearch([_res("A.2020.1080p")])
    cfg = Config(saved_searches=[SavedSearch(name="A", query="a")])
    assert await fetch_feed(cfg, search) is None
