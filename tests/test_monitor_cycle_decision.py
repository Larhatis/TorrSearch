from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from torsearch.config import Config, LibraryConfig, MonitorConfig
from torsearch.db.database import Database
from torsearch.library.blacklist import Blacklist
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, SearchResult, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import run_movie_cycle, run_series_cycle


class FakeSearchService:
    def __init__(self, canned: dict[str, list[SearchResult]] | None = None):
        self._canned = canned or {}
        self.searched: list[tuple[str, Category]] = []

    async def search(self, query: str, category: Category) -> list[SearchResult]:
        self.searched.append((query, category))
        return self._canned.get(query, [])


class FakeTransmission:
    def __init__(self):
        self.added: list[tuple[str, str | None]] = []

    async def add(self, url: str, download_dir: str | None = None) -> None:
        self.added.append((url, download_dir))


def _res(title: str, size: int = 1_000_000_000, seeders: int = 10, url: str = "") -> SearchResult:
    return SearchResult(
        title=title,
        size=size,
        seeders=seeders,
        leechers=1,
        source="indexer1",
        category=Category.MOVIES,
        download_url=url or f"magnet:?xt={title}",
        infohash=f"hash-{title}",
    )


@pytest.mark.asyncio
async def test_movie_cycle_rejects_cam_and_sequel(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    lib = MovieLibrary(db)
    history = MonitorHistory(db)
    bl = Blacklist(db)

    lib.add(WantedMovie(
        tmdb_id=1, title="Avatar", year="2009", added_at=datetime.now(UTC),
    ))

    canned = {
        "Avatar 2009": [
            _res("Avatar.The.Way.of.Water.2022.MULTi.1080p"),  # Sequel -> reject
            _res("Avatar.2009.CAM.XViD"),                       # Banned source -> reject
            _res("Avatar.2009.TRUEFRENCH.1080p.BluRay"),       # Valid -> accept
        ]
    }
    search = FakeSearchService(canned)
    tx = FakeTransmission()
    cfg = Config(
        monitor=MonitorConfig(enabled=True),
        library=LibraryConfig(qualities=["1080p"]),
    )

    records = await run_movie_cycle(cfg, lib, search, tx, history, blacklist=bl)
    assert len(records) == 1
    assert records[0].title == "Avatar.2009.TRUEFRENCH.1080p.BluRay"
    assert len(tx.added) == 1


@pytest.mark.asyncio
async def test_movie_cycle_searches_with_original_title(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    lib = MovieLibrary(db)
    history = MonitorHistory(db)
    bl = Blacklist(db)

    lib.add(WantedMovie(
        tmdb_id=2, title="Le Parrain", original_title="The Godfather",
        year="1972", added_at=datetime.now(UTC),
    ))

    canned = {
        "Le Parrain 1972": [],  # Nothing with French title
        "The Godfather 1972": [
            _res("The.Godfather.1972.MULTi.1080p.BluRay"),
        ],
    }
    search = FakeSearchService(canned)
    tx = FakeTransmission()
    cfg = Config(
        monitor=MonitorConfig(enabled=True),
        library=LibraryConfig(qualities=["1080p"]),
    )

    records = await run_movie_cycle(cfg, lib, search, tx, history, blacklist=bl)
    assert len(records) == 1
    assert records[0].title == "The.Godfather.1972.MULTi.1080p.BluRay"


@pytest.mark.asyncio
async def test_movie_cycle_blacklists_failed_grab_on_rehunt(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    lib = MovieLibrary(db)
    history = MonitorHistory(db)
    bl = Blacklist(db)

    old_at = datetime.now(UTC) - timedelta(hours=50)
    movie = WantedMovie(
        tmdb_id=3, title="Dune", year="2021", status="grabbed",
        grabbed_title="Dune.2021.Dead.Torrent.1080p", grabbed_at=old_at,
        added_at=old_at,
    )
    lib.add(movie)

    # Fake Jellyfin enabled but returns empty (meaning download failed and movie was not added to Jellyfin)
    class FakeJellyfin:
        enabled = True
        async def owned(self):
            return {}

    canned = {
        "Dune 2021": [
            _res("Dune.2021.Dead.Torrent.1080p"),
            _res("Dune.2021.MULTi.1080p.BluRay"),
        ]
    }
    search = FakeSearchService(canned)
    tx = FakeTransmission()
    cfg = Config(
        monitor=MonitorConfig(enabled=True, regrab_hours=48),
        library=LibraryConfig(qualities=["1080p"]),
    )

    records = await run_movie_cycle(cfg, lib, search, tx, history, jellyfin=FakeJellyfin(), blacklist=bl)
    assert len(records) == 1
    assert records[0].title == "Dune.2021.MULTi.1080p.BluRay"
    # The previous dead torrent is now blacklisted
    assert bl.is_blacklisted(None, "Dune.2021.Dead.Torrent.1080p")


@pytest.mark.asyncio
async def test_series_cycle_rejects_false_positive_titles(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    series_lib = SeriesLibrary(db)
    history = MonitorHistory(db)
    bl = Blacklist(db)

    series_lib.add(WantedSeries(
        tmdb_id=10, title="Lost", added_at=datetime.now(UTC),
    ))

    canned = {
        "Lost": [
            _res("Lost.in.Space.S01E01.FRENCH.1080p"),  # False positive -> reject
            _res("Lost.S01E01.FRENCH.1080p"),          # Valid -> accept
        ]
    }
    search = FakeSearchService(canned)
    tx = FakeTransmission()
    cfg = Config(
        monitor=MonitorConfig(enabled=True),
        library=LibraryConfig(qualities=["1080p"]),
    )

    records = await run_series_cycle(cfg, series_lib, search, tx, history, blacklist=bl)
    assert len(records) == 1
    assert records[0].title == "Lost.S01E01.FRENCH.1080p"


@pytest.mark.asyncio
async def test_series_skips_marked_seasons(tmp_path):
    series_lib = SeriesLibrary(tmp_path / "series.db")
    history = MonitorHistory(tmp_path / "history.db")
    # Series with Season 1 marked as acquired
    series_lib.add(
        WantedSeries(
            tmdb_id=4607,
            title="Lost",
            added_at=datetime.now(UTC),
            grabbed=["S01", "S01E01", "S01E02"],
        )
    )

    class FakeTmdb:
        enabled = True

        async def episodes(self, tv_id):
            return {"S01E01", "S01E02", "S02E01"}

    canned = {
        "Lost": [
            _res("Lost.S01E01.FRENCH.1080p"),
            _res("Lost.S02E01.FRENCH.1080p"),
        ]
    }
    search = FakeSearchService(canned)
    tx = FakeTransmission()
    cfg = Config(
        monitor=MonitorConfig(enabled=True),
        library=LibraryConfig(qualities=["1080p"]),
    )

    records = await run_series_cycle(cfg, series_lib, search, tx, history, tmdb=FakeTmdb())
    assert len(records) == 1
    assert records[0].title == "Lost.S02E01.FRENCH.1080p"



class FakeTransmissionWithList(FakeTransmission):
    def __init__(self, names):
        super().__init__()
        self._names = names

    async def list_torrents(self):
        from torsearch.transmission.client import TorrentInfo

        return [
            TorrentInfo(id=i, name=n, percent=40.0, status="downloading", down_rate=1, up_rate=0, size=1)
            for i, n in enumerate(self._names)
        ]


class FakeJellyfinEmpty:
    enabled = True

    async def owned(self):
        return {}


@pytest.mark.asyncio
async def test_grabbed_movie_still_in_transmission_is_not_rehunted(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    lib = MovieLibrary(db)
    bl = Blacklist(db)
    lib.add(WantedMovie(tmdb_id=1, title="Spider-Man : Brand New Day", original_title="Spider-Man: Brand New Day",
                        year="2026", added_at=datetime.now(UTC) - timedelta(days=20)))
    lib.mark_grabbed(1, "Spider.Man.Brand.New.Day.2026.MULTI.2160p.WEB-GRP", datetime.now(UTC) - timedelta(days=3))
    search = FakeSearchService({"Spider-Man : Brand New Day 2026": [_res("Spider.Man.Brand.New.Day.2026.MULTi.2160p.WEB-X")]})
    tx = FakeTransmissionWithList(["Spider-Man.Brand.New.Day.2026.MULTi.2160p.WEB-DL.H265-GRP.mkv"])
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["2160p"]))

    records = await run_movie_cycle(cfg, lib, search, tx, MonitorHistory(db), jellyfin=FakeJellyfinEmpty(), blacklist=bl)
    assert records == []
    assert tx.added == []
    assert bl.list() == []
    assert lib.get(1).status == "grabbed"


@pytest.mark.asyncio
async def test_grabbed_movie_absent_everywhere_is_rehunted(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=1, title="Avatar", year="2009", added_at=datetime.now(UTC) - timedelta(days=20)))
    lib.mark_grabbed(1, "Avatar.2009.MULTI.1080p.WEB-GRP", datetime.now(UTC) - timedelta(days=3))
    search = FakeSearchService({"Avatar 2009": [_res("Avatar.2009.MULTi.1080p.BluRay-X")]})
    tx = FakeTransmissionWithList(["Other.Movie.2020.1080p.mkv"])
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["1080p"]))

    records = await run_movie_cycle(cfg, lib, search, tx, MonitorHistory(db), jellyfin=FakeJellyfinEmpty(),
                                    blacklist=Blacklist(db))
    assert [r.title for r in records] == ["Avatar.2009.MULTi.1080p.BluRay-X"]
