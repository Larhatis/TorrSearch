from __future__ import annotations

from datetime import UTC, datetime, timedelta

from torsearch.config import Config, LibraryConfig, MonitorConfig
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory, MonitorRecord
from torsearch.monitor.runner import run_movie_cycle, run_series_cycle
from torsearch.monitor.schedule import SearchSchedule
from torsearch.parser.release import parse_release
from torsearch.search.decision import release_group, replacement_reason

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _reason(candidate, previous, at=NOW - timedelta(days=1), upgrades=False):
    return replacement_reason(
        parse_release(candidate), previous, at, NOW,
        qualities=["2160p", "1080p", "720p"], upgrades=upgrades,
    )


def test_release_group():
    assert release_group("Show.S01E01.1080p.WEB.H264-GRP") == "GRP"
    assert release_group("Show.S01E01.1080p.WEB.H264-GRP.mkv") == "GRP"
    assert release_group("Show S01E01 1080p") is None


def test_repack_same_resolution_and_group_accepted():
    assert _reason("Show.S01E01.REPACK.MULTi.1080p.WEB-GRP", "Show.S01E01.MULTi.1080p.WEB-GRP") == "repack"
    assert _reason("Show.S01E01.PROPER.MULTi.1080p.WEB", "Show.S01E01.MULTi.1080p.WEB") == "repack"


def test_repack_rejected_when_other_group_resolution_or_too_old():
    assert _reason("Show.S01E01.REPACK.MULTi.1080p.WEB-OTHER", "Show.S01E01.MULTi.1080p.WEB-GRP") is None
    assert _reason("Show.S01E01.REPACK.MULTi.720p.WEB-GRP", "Show.S01E01.MULTi.1080p.WEB-GRP") is None
    assert _reason("Show.S01E01.REPACK.MULTi.1080p.WEB-GRP", "Show.S01E01.MULTi.1080p.WEB-GRP",
                   at=NOW - timedelta(days=30)) is None


def test_repack_of_a_repack_is_ignored():
    assert _reason("Show.S01E01.REPACK.MULTi.1080p.WEB-GRP", "Show.S01E01.PROPER.MULTi.1080p.WEB-GRP") is None


def test_upgrade_needs_option_better_quality_and_no_worse_language():
    better = "Show.S01E01.MULTi.2160p.WEB-GRP"
    assert _reason(better, "Show.S01E01.MULTi.1080p.WEB-GRP") is None  # upgrades off
    assert _reason(better, "Show.S01E01.MULTi.1080p.WEB-GRP", upgrades=True) == "upgrade"
    assert _reason("Show.S01E01.VOSTFR.2160p.WEB-GRP", "Show.S01E01.MULTi.1080p.WEB-GRP", upgrades=True) is None
    assert _reason("Show.S01E01.MULTi.1080p.WEB-X", "Show.S01E01.MULTi.1080p.WEB-GRP", upgrades=True) is None


# --- cycles ---------------------------------------------------------------------------

def _res(title, category=Category.TV):
    return SearchResult(
        title=title, size=1_000_000, seeders=10, leechers=1, source="t1", category=category,
        download_url=f"magnet:?xt=urn:btih:{title}", infohash=f"hash-{title}",
    )


class NoSearch:
    async def search(self, query, category=Category.ALL):
        raise AssertionError("no targeted search expected")


class FakeTransmission:
    def __init__(self):
        self.added: list[str] = []

    async def add(self, url, download_dir=None):
        self.added.append(url)


class FakeTmdb:
    enabled = True

    async def air_dates(self, tv_id):
        return {"S01E01": "2026-10-20"}


def _cfg(upgrades=False):
    return Config(
        monitor=MonitorConfig(enabled=True),
        library=LibraryConfig(qualities=["2160p", "1080p"], upgrades=upgrades),
    )


async def test_series_complete_takes_repack_from_feed(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = SeriesLibrary(db)
    lib.add(WantedSeries(tmdb_id=1, title="Severance", added_at=NOW, grabbed=["S01E01"]))
    history = MonitorHistory(db)
    history.add(MonitorRecord(
        search="Severance", title="Severance.S01E01.MULTi.1080p.WEB-GRP", source="t1",
        download_url="magnet:old", kind="grabbed", at=datetime.now(UTC) - timedelta(days=2),
    ))
    tx = FakeTransmission()
    feed = [_res("Severance.S01E01.REPACK.MULTi.1080p.WEB-GRP")]

    records = await run_series_cycle(
        _cfg(), lib, NoSearch(), tx, history, tmdb=FakeTmdb(), feed=feed, schedule=SearchSchedule(),
    )
    assert [r.title for r in records] == ["Severance.S01E01.REPACK.MULTi.1080p.WEB-GRP"]

    # Next cycle: the repack is now the latest grab, nothing more is taken.
    again = await run_series_cycle(
        _cfg(), lib, NoSearch(), tx, history, tmdb=FakeTmdb(), feed=feed, schedule=SearchSchedule(),
    )
    assert again == []


async def test_series_upgrade_from_feed_when_enabled(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = SeriesLibrary(db)
    lib.add(WantedSeries(tmdb_id=1, title="Severance", added_at=NOW, grabbed=["S01E01"]))
    history = MonitorHistory(db)
    history.add(MonitorRecord(
        search="Severance", title="Severance.S01E01.MULTi.1080p.WEB-GRP", source="t1",
        download_url="magnet:old", kind="grabbed", at=datetime.now(UTC) - timedelta(days=10),
    ))
    feed = [_res("Severance.S01E01.MULTi.1080p.WEB-OTHER"), _res("Severance.S01E01.MULTi.2160p.WEB-GRP")]

    off = await run_series_cycle(_cfg(), lib, NoSearch(), FakeTransmission(), history,
                                 tmdb=FakeTmdb(), feed=feed, schedule=SearchSchedule())
    assert off == []
    on = await run_series_cycle(_cfg(upgrades=True), lib, NoSearch(), FakeTransmission(), history,
                                tmdb=FakeTmdb(), feed=feed, schedule=SearchSchedule())
    assert [r.title for r in on] == ["Severance.S01E01.MULTi.2160p.WEB-GRP"]


async def test_movie_repack_from_feed(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=NOW))
    lib.mark_grabbed(1, "Avatar.2009.MULTi.1080p.BluRay-GRP", datetime.now(UTC) - timedelta(days=1))
    tx = FakeTransmission()
    feed = [_res("Avatar.2009.REPACK.MULTi.1080p.BluRay-GRP", Category.MOVIES)]

    records = await run_movie_cycle(_cfg(), lib, NoSearch(), tx, MonitorHistory(db),
                                    feed=feed, schedule=SearchSchedule())
    assert [r.title for r in records] == ["Avatar.2009.REPACK.MULTi.1080p.BluRay-GRP"]
    assert lib.get(1).grabbed_title == "Avatar.2009.REPACK.MULTi.1080p.BluRay-GRP"


def test_upgrade_ignores_old_grabs():
    assert _reason("Show.S01E01.MULTi.2160p.WEB-GRP", "Show.S01E01.MULTi.1080p.WEB-GRP",
                   at=NOW - timedelta(days=60), upgrades=True) is None
