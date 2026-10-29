from __future__ import annotations

from datetime import UTC, datetime

from torsearch.config import Config, LibraryConfig, MonitorConfig, PathsConfig
from torsearch.db.database import Database
from torsearch.library.episodes import build_movie_download_dir
from torsearch.library.movies import MovieLibrary
from torsearch.models import Category, SearchResult, WantedMovie
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import run_movie_cycle


def test_movie_folder_follows_jellyfin_convention():
    assert build_movie_download_dir("/downloads/disk1/Films", "Spider-Man : Brand New Day", "2026", 969681) == (
        "/downloads/disk1/Films/Spider-Man - Brand New Day (2026) [tmdbid-969681]"
    )
    assert build_movie_download_dir("/films/", "Heat", None, 949) == "/films/Heat [tmdbid-949]"
    assert build_movie_download_dir("/f", "Dune: Part Two", "2024", None) == "/f/Dune - Part Two (2024)"
    assert build_movie_download_dir(None, "Dune", "2024", 1) is None
    assert build_movie_download_dir("/films", "Avatar", "2009/../../../../srv/x", 1) == "/films/Avatar [tmdbid-1]"
    assert build_movie_download_dir("/films", "..", None, None) == "/films/Unknown"
    assert build_movie_download_dir("/f", 'Who? "Me" / You', "2020", 1) == "/f/Who Me You (2020) [tmdbid-1]"


class FakeSearch:
    async def search(self, query, category=Category.ALL):
        return [SearchResult(title="Avatar.2009.MULTi.1080p.BluRay-GRP", size=1, seeders=10, leechers=0,
                             source="t", category=Category.MOVIES, download_url="magnet:a")]


class FakeTransmission:
    def __init__(self):
        self.added = []

    async def add(self, url, download_dir=None):
        self.added.append((url, download_dir))


async def test_monitor_grabs_movie_into_its_own_folder(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    lib = MovieLibrary(db)
    lib.add(WantedMovie(tmdb_id=19995, title="Avatar", year="2009", added_at=datetime.now(UTC)))
    tx = FakeTransmission()
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["1080p"]),
                 paths=PathsConfig(by_category={"movies": "/downloads/disk1/Films"}))
    await run_movie_cycle(cfg, lib, FakeSearch(), tx, MonitorHistory(db))
    assert tx.added == [("magnet:a", "/downloads/disk1/Films/Avatar (2009) [tmdbid-19995]")]
