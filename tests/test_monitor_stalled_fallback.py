from datetime import UTC, datetime, timedelta

from torsearch.config import Config, MonitorConfig
from torsearch.library.blacklist import Blacklist
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedMovie, WantedSeries
from torsearch.monitor.runner import handle_stalled_torrents
from torsearch.transmission.client import TorrentInfo


class FakeTransmission:
    def __init__(self, torrents=None):
        self._torrents = list(torrents or [])
        self.removed = []

    async def list_torrents(self):
        return list(self._torrents)

    async def remove(self, torrent_id: int, delete_data: bool = False):
        self.removed.append((torrent_id, delete_data))
        self._torrents = [t for t in self._torrents if t.id != torrent_id]


async def test_stalled_torrent_purged_and_blacklisted_and_movie_unmarked(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    old_added = now - timedelta(hours=3)

    t_stalled = TorrentInfo(
        id=101,
        name="Dune.Part.Two.2024.1080p.WEBRip",
        percent=0.0,
        status="downloading",
        down_rate=0,
        up_rate=0,
        size=2_000_000_000,
        peers_connected=0,
        peers_sending=0,
        info_hash="aabbccddee",
        date_added=old_added,
    )

    tr = FakeTransmission([t_stalled])
    bl = Blacklist(tmp_path / "blacklist.db")
    mov_lib = MovieLibrary(tmp_path / "movies.json")
    mov_lib.add(WantedMovie(tmdb_id=693134, title="Dune : Deuxieme partie", added_at=now))
    mov_lib.mark_grabbed(693134, "Dune.Part.Two.2024.1080p.WEBRip", old_added)

    cfg = Config(monitor=MonitorConfig(stalled_hours=2))

    handled = await handle_stalled_torrents(
        transmission=tr,
        library=mov_lib,
        blacklist=bl,
        config=cfg,
        now=now,
    )

    assert handled == ["Dune.Part.Two.2024.1080p.WEBRip"]
    assert tr.removed == [(101, True)]
    assert bl.is_blacklisted("aabbccddee", "Dune.Part.Two.2024.1080p.WEBRip") is True

    # Movie is unmarked and ready for next grab
    m = mov_lib.get(693134)
    assert m.status == "wanted"
    assert m.grabbed_title is None


async def test_errored_torrent_purged_immediately(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_error = TorrentInfo(
        id=102,
        name="Severance.S01E01.1080p",
        percent=12.0,
        status="error",
        down_rate=0,
        up_rate=0,
        size=1_000_000_000,
        error_string="Tracker returned 404 Not Found",
        info_hash="1122334455",
        date_added=now - timedelta(minutes=10),
    )

    tr = FakeTransmission([t_error])
    bl = Blacklist(tmp_path / "blacklist.db")
    series_lib = SeriesLibrary(tmp_path / "series.json")
    series_lib.add(WantedSeries(tmdb_id=1, title="Severance", added_at=now, grabbed=["S01E01"]))

    handled = await handle_stalled_torrents(
        transmission=tr,
        series_library=series_lib,
        blacklist=bl,
        now=now,
    )

    assert handled == ["Severance.S01E01.1080p"]
    assert tr.removed == [(102, True)]
    assert bl.is_blacklisted("1122334455", "Severance.S01E01.1080p") is True
    # S01E01 was unmarked from series
    assert series_lib.get(1).grabbed == []


async def test_fresh_torrent_under_grace_period_is_not_purged(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_fresh = TorrentInfo(
        id=103,
        name="Fresh.Movie.2024",
        percent=0.0,
        status="downloading",
        down_rate=0,
        up_rate=0,
        size=2_000_000_000,
        peers_connected=0,
        peers_sending=0,
        date_added=now - timedelta(minutes=30),  # only 30m old, stalled_hours is 2h
    )

    tr = FakeTransmission([t_fresh])
    bl = Blacklist(tmp_path / "blacklist.db")
    cfg = Config(monitor=MonitorConfig(stalled_hours=2))

    handled = await handle_stalled_torrents(transmission=tr, blacklist=bl, config=cfg, now=now)
    assert handled == []
    assert tr.removed == []


async def test_paused_torrent_is_not_purged(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_paused = TorrentInfo(
        id=104,
        name="Paused.Movie.2024",
        percent=0.0,
        status="stopped",
        down_rate=0,
        up_rate=0,
        size=2_000_000_000,
        peers_connected=0,
        peers_sending=0,
        date_added=now - timedelta(hours=5),
    )

    tr = FakeTransmission([t_paused])
    handled = await handle_stalled_torrents(transmission=tr, now=now)
    assert handled == []
    assert tr.removed == []
