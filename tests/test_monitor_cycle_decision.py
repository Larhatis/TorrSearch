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
