from datetime import UTC, datetime, timedelta

from torsearch.config import Config, MonitorConfig
from torsearch.library.blacklist import Blacklist
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedMovie, WantedSeries
from torsearch.monitor.grabs import GrabRegistry
from torsearch.monitor.stalled import DailyNotice, handle_stalled_torrents, tracker_forgot_torrent
from torsearch.transmission.client import TorrentInfo

ON = Config(monitor=MonitorConfig(enabled=True, stalled_hours=2))


def _auto(tmp_path, *sent, origin="auto"):
    """A registry where ``sent`` torrents (or bare hashes) were sent by the surveillance (or by hand).

    A torrent is recorded at its Transmission ``date_added``, as a real send would be.
    """
    g = GrabRegistry(tmp_path / "grabs.db")
    for item in sent:
        if isinstance(item, TorrentInfo):
            g.record(item.info_hash, item.name, origin, at=item.date_added)
        else:
            g.record(item, "t", origin)
    return g


class FakeNotifier:
    def __init__(self):
        self.messages: list[tuple[str, str]] = []
        self.records = []

    async def notify_message(self, channels, title, body):
        self.messages.append((title, body))

    async def notify(self, channels, record):
        self.records.append(record)


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

    handled = await handle_stalled_torrents(
        transmission=tr,
        library=mov_lib,
        blacklist=bl,
        config=ON,
        now=now,
        grabs=_auto(tmp_path, t_stalled),
    )

    assert handled == ["Dune.Part.Two.2024.1080p.WEBRip"]
    assert tr.removed == [(101, True)]
    assert bl.is_blacklisted("aabbccddee", "Dune.Part.Two.2024.1080p.WEBRip") is True

    # Movie is unmarked and ready for next grab
    m = mov_lib.get(693134)
    assert m.status == "wanted"
    assert m.grabbed_title is None


async def test_errored_torrent_purged_after_grace_period(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_error = TorrentInfo(
        id=102,
        name="Severance.S01E01.1080p",
        percent=12.0,
        status="downloading",
        down_rate=0,
        up_rate=0,
        size=1_000_000_000,
        error_string="Unregistered torrent",
        error_code=2,
        info_hash="1122334455",
        date_added=now - timedelta(hours=3),
    )

    tr = FakeTransmission([t_error])
    bl = Blacklist(tmp_path / "blacklist.db")
    series_lib = SeriesLibrary(tmp_path / "series.json")
    series_lib.add(WantedSeries(tmdb_id=1, title="Severance", added_at=now, grabbed=["S01E01"]))

    grabs = _auto(tmp_path, t_error)
    handled = await handle_stalled_torrents(
        transmission=tr,
        series_library=series_lib,
        blacklist=bl,
        config=ON,
        now=now,
        grabs=grabs,
    )

    assert handled == ["Severance.S01E01.1080p"]
    assert tr.removed == [(102, True)]
    assert bl.is_blacklisted("1122334455", "Severance.S01E01.1080p") is True
    # S01E01 was unmarked from series
    assert series_lib.get(1).grabbed == []
    assert grabs.get("1122334455") is None  # forgotten with the torrent


async def test_fresh_torrent_under_grace_period_is_not_purged(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_fresh = TorrentInfo(
        id=103,
        name="Fresh.Movie.2024",
        info_hash="h103",
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
    handled = await handle_stalled_torrents(transmission=tr, blacklist=bl, config=ON, now=now,
                                            grabs=_auto(tmp_path, t_fresh))
    assert handled == []
    assert tr.removed == []


async def test_paused_torrent_is_not_purged(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    t_paused = TorrentInfo(
        id=104,
        name="Paused.Movie.2024",
        info_hash="h104",
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
    handled = await handle_stalled_torrents(transmission=tr, now=now, config=ON, grabs=_auto(tmp_path, t_paused))
    assert handled == []
    assert tr.removed == []


def _fresh(**over):
    base = dict(id=7, name="MobLand.S02E01.MULTi.2160p.WEB-GRP", percent=0.0, status="downloading",
                down_rate=0, up_rate=0, size=1, peers_connected=0, peers_sending=0, info_hash="h7")
    base.update(over)
    return TorrentInfo(**base)


async def test_torrent_with_unknown_age_is_never_purged(tmp_path):
    tr = FakeTransmission([_fresh(date_added=None)])
    bl = Blacklist(tmp_path / "bl.db")
    handled = await handle_stalled_torrents(tr, blacklist=bl, config=ON, grabs=_auto(tmp_path, "h7"))
    assert handled == []
    assert tr.removed == []
    assert bl.list() == []


async def test_fresh_torrent_in_error_is_not_purged(tmp_path):
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    tr = FakeTransmission([_fresh(error_string="Tracker gave HTTP response code 502",
                                  date_added=now - timedelta(minutes=5))])
    handled = await handle_stalled_torrents(tr, blacklist=Blacklist(tmp_path / "bl.db"),
                                            config=ON, now=now, grabs=_auto(tmp_path, "h7"))
    assert handled == []
    assert tr.removed == []


async def test_purge_forgets_the_grab_so_the_gap_is_hunted_again(tmp_path):
    from torsearch.db.database import Database
    from torsearch.monitor.history import MonitorHistory, MonitorRecord

    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    db = Database(tmp_path / "db.sqlite")
    history = MonitorHistory(db)
    # Tracker title and torrent name differ; the pack is matched by title + episodes.
    history.add(MonitorRecord(search="MobLand", title="MobLand.S01.MULTi.VFF.2160p.WEBRip.x265-BATGirl",
                              source="t", download_url="magnet:a", kind="grabbed", at=now - timedelta(hours=3)))
    history.add(MonitorRecord(search="MobLand", title="MobLand.S02E05.MULTi.2160p.WEB-GRP", source="t",
                              infohash="keep", download_url="magnet:b", kind="grabbed", at=now - timedelta(hours=3)))
    history.add(MonitorRecord(search="Lost", title="Lost.S01E01.1080p-X", source="t", infohash="dead",
                              download_url="magnet:c", kind="grabbed", at=now - timedelta(hours=3)))
    series = SeriesLibrary(db)
    series.add(WantedSeries(tmdb_id=1, title="MobLand", added_at=now,
                            grabbed=["S01E01", "S01E02", "S01E10", "S02E05"]))
    torrents = [
        _fresh(id=1, name="MobLand.S01.4KLight.DV.HDR10Plus.x265", info_hash="other",
               date_added=now - timedelta(hours=3)),
        _fresh(id=2, name="Lost.S01E01.1080p-X.mkv", info_hash="DEAD", date_added=now - timedelta(hours=3)),
    ]

    handled = await handle_stalled_torrents(
        FakeTransmission(torrents), series_library=series, blacklist=Blacklist(db), history=history,
        config=ON, now=now, grabs=_auto(tmp_path, *torrents),
    )
    assert len(handled) == 2
    assert [r.title for r in history.records()] == ["MobLand.S02E05.MULTi.2160p.WEB-GRP"]
    assert series.get(1).grabbed == ["S02E05"]  # the whole season pack is unmarked


# --- Chantier 10: only the surveillance's own, certainly dead torrents are purged ---

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _old(id, **over):
    """A torrent added 3 h ago (past the 2 h grace), dead by default (0 %, no peer)."""
    base = dict(id=id, name=f"Some.Movie.{id}.2024.1080p.WEB-GRP", percent=0.0, status="downloading",
                down_rate=0, up_rate=0, size=1, peers_connected=0, peers_sending=0, info_hash=f"h{id}",
                date_added=NOW - timedelta(hours=3))
    base.update(over)
    return TorrentInfo(**base)


async def _purge(tmp_path, torrents, grabs="auto", config=ON, notifier=None, notice=None):
    tr = FakeTransmission(torrents)
    if grabs == "auto":
        grabs = _auto(tmp_path, *torrents)
    handled = await handle_stalled_torrents(tr, blacklist=Blacklist(tmp_path / "bl.db"), config=config, now=NOW,
                                            grabs=grabs, notifier=notifier, notice=notice)
    return handled, tr


async def test_nothing_purged_when_monitor_disabled(tmp_path):
    handled, tr = await _purge(tmp_path, [_old(1)], config=Config(monitor=MonitorConfig(enabled=False)))
    assert handled == [] and tr.removed == []


async def test_torrent_not_sent_by_surveillance_is_kept(tmp_path):
    handled, tr = await _purge(tmp_path, [_old(1)], grabs=_auto(tmp_path))
    assert handled == [] and tr.removed == []


async def test_manual_download_is_kept(tmp_path):
    handled, tr = await _purge(tmp_path, [_old(1)], grabs=_auto(tmp_path, "h1", origin="manual"))
    assert handled == [] and tr.removed == []


async def test_nothing_purged_without_registry(tmp_path):
    handled, tr = await _purge(tmp_path, [_old(1)], grabs=None)
    assert handled == [] and tr.removed == []


async def test_tracker_warning_does_not_purge(tmp_path):
    t = _old(1, percent=40.0, error_code=1, error_string="Could not connect to tracker")
    handled, tr = await _purge(tmp_path, [t])
    assert handled == [] and tr.removed == []


async def test_local_error_does_not_purge(tmp_path):
    t = _old(1, percent=40.0, error_code=3, error_string="No space left on device")
    handled, tr = await _purge(tmp_path, [t])
    assert handled == [] and tr.removed == []


async def test_unregistered_torrent_is_purged(tmp_path):
    t = _old(1, percent=40.0, error_code=2, error_string="Unregistered torrent")
    handled, tr = await _purge(tmp_path, [t])
    assert handled == [t.name] and tr.removed == [(1, True)]


async def test_dead_auto_torrent_is_purged_and_forgotten(tmp_path):
    grabs = _auto(tmp_path, _old(1))
    handled, tr = await _purge(tmp_path, [_old(1)], grabs=grabs)
    assert tr.removed == [(1, True)]
    assert grabs.get("h1") is None


async def test_paused_torrent_in_error_is_kept(tmp_path):
    t = _old(1, status="stopped", percent=40.0, error_code=2, error_string="Unregistered torrent")
    handled, tr = await _purge(tmp_path, [t])
    assert handled == [] and tr.removed == []


async def test_three_candidates_are_purged(tmp_path):
    handled, tr = await _purge(tmp_path, [_old(1), _old(2), _old(3)])
    assert len(handled) == 3 and len(tr.removed) == 3


async def test_more_than_three_candidates_suspends_the_purge(tmp_path):
    notifier = FakeNotifier()
    handled, tr = await _purge(tmp_path, [_old(i) for i in range(1, 5)], notifier=notifier)
    assert handled == [] and tr.removed == []
    assert notifier.messages == [(
        "Purge suspendue",
        "4 torrents semblent bloques en meme temps (panne reseau ou VPN ?). Aucun n'a ete supprime.",
    )]


async def test_suspension_is_notified_once_a_day(tmp_path):
    notifier, notice = FakeNotifier(), DailyNotice()
    torrents = [_old(i) for i in range(1, 5)]
    await _purge(tmp_path, torrents, notifier=notifier, notice=notice)
    await _purge(tmp_path, torrents, notifier=notifier, notice=notice)
    assert len(notifier.messages) == 1


def test_daily_notice():
    from datetime import date

    notice = DailyNotice()
    assert notice.allow(date(2026, 11, 1)) is True
    assert notice.allow(date(2026, 11, 1)) is False
    assert notice.allow(date(2026, 11, 2)) is True


def test_tracker_forgot_torrent():
    assert tracker_forgot_torrent(2, "Unregistered torrent")
    assert tracker_forgot_torrent(2, "Torrent not registered with this tracker")
    assert tracker_forgot_torrent(1, "torrent introuvable")
    assert not tracker_forgot_torrent(3, "unregistered")
    assert not tracker_forgot_torrent(2, "Tracker returned 404 Not Found")
    assert not tracker_forgot_torrent(0, "")


async def test_monitor_runner_purges_with_its_registry(tmp_path):
    from torsearch.monitor.history import MonitorHistory
    from torsearch.monitor.runner import MonitorRunner

    dead = _old(1, date_added=datetime.now(UTC) - timedelta(hours=3))
    tr = FakeTransmission([dead])

    class Ctx:
        config = ON
        search_service = object()
        transmission = tr

    await MonitorRunner(Ctx(), MonitorHistory(tmp_path / "m.json"), grabs=_auto(tmp_path, dead)).run_once()
    assert tr.removed == [(1, True)]


# --- Final review fixes ---


async def test_duplicate_add_of_an_older_torrent_is_kept(tmp_path):
    # Added by hand weeks ago; the surveillance later "sends" the same release: Transmission
    # answers with the existing torrent, so the registry entry is younger than the torrent.
    t = _old(1, date_added=NOW - timedelta(days=30))
    grabs = GrabRegistry(tmp_path / "g.db")
    grabs.record(t.info_hash, t.name, "auto", at=NOW - timedelta(hours=1))
    handled, tr = await _purge(tmp_path, [t], grabs=grabs)
    assert handled == [] and tr.removed == []


async def test_unregistered_but_still_downloading_is_kept(tmp_path):
    t = _old(1, percent=85.0, down_rate=5_000_000, peers_sending=12, error_code=2,
             error_string="Unregistered torrent")
    handled, tr = await _purge(tmp_path, [t])
    assert handled == [] and tr.removed == []


async def test_queued_or_checking_torrent_is_kept(tmp_path):
    torrents = [_old(1, status="download pending"), _old(2, status="checking"), _old(3, status="check pending")]
    handled, tr = await _purge(tmp_path, torrents)
    assert handled == [] and tr.removed == []


async def test_failed_removal_changes_nothing_else(tmp_path):
    # The torrent is still in Transmission: blacklisting it, unmarking the movie or forgetting the
    # grab would hunt a second copy next to it.
    class StuckTransmission(FakeTransmission):
        async def remove(self, torrent_id, delete_data=False):
            raise RuntimeError("connection refused")

    t = _old(1)
    bl, grabs, notifier = Blacklist(tmp_path / "bl.db"), _auto(tmp_path, t), FakeNotifier()
    lib = MovieLibrary(tmp_path / "movies.json")
    lib.add(WantedMovie(tmdb_id=1, title="Some Movie", added_at=NOW))
    lib.mark_grabbed(1, t.name, t.date_added)

    handled = await handle_stalled_torrents(StuckTransmission([t]), library=lib, blacklist=bl, notifier=notifier,
                                            config=ON, now=NOW, grabs=grabs)

    assert handled == []
    assert bl.is_blacklisted(t.info_hash, t.name) is False
    assert lib.get(1).status == "grabbed"
    assert grabs.get(t.info_hash) is not None
    assert notifier.records == []
