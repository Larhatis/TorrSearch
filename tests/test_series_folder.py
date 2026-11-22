"""A followed series is filed in the folder where it already lives (Jellyfin, Transmission)."""
from __future__ import annotations

from datetime import UTC, datetime

from torsearch.library.series import SeriesLibrary
from torsearch.library.series_folder import (
    find_series_folder,
    folder_in_base,
    map_library_path,
    new_series_folder,
    series_folder,
)
from torsearch.models import WantedSeries
from torsearch.transmission.client import TorrentInfo

BASE = "/downloads/disk2"
NOW = datetime(2026, 11, 22, tzinfo=UTC)
RICK = WantedSeries(tmdb_id=60625, title="Rick et Morty", original_title="Rick and Morty", year="2013",
                    added_at=NOW)


def _torrent(name, download_dir, id=1):
    return TorrentInfo(id=id, name=name, percent=100.0, status="seeding", down_rate=0, up_rate=0, size=1,
                       download_dir=download_dir)


class FakeJellyfin:
    enabled = True

    def __init__(self, paths=None, error=False):
        self._paths = paths or {}
        self._error = error
        self.calls = 0

    async def series_paths(self, tmdb_id):
        self.calls += 1
        if self._error:
            raise RuntimeError("down")
        return self._paths.get(tmdb_id, [])


class FakeTransmission:
    def __init__(self, torrents=(), error=False):
        self._torrents = list(torrents)
        self._error = error

    async def list_torrents(self):
        if self._error:
            raise RuntimeError("down")
        return list(self._torrents)


def test_map_library_path_compares_paths_from_the_end():
    assert map_library_path("/media/disk2/Rick.and.Morty", BASE) == "/downloads/disk2/Rick.and.Morty"
    assert map_library_path("/media/disk2/Series/Foo", "/downloads/disk2/Series") == "/downloads/disk2/Series/Foo"
    assert map_library_path("/media/disk1/Films/Foo", BASE) is None
    assert map_library_path("/media/disk2/Shows/Foo", BASE) is None  # not directly in the TV folder
    assert map_library_path("/media/disk2", BASE) is None


def test_folder_in_base_is_the_first_folder_below_the_tv_folder():
    assert folder_in_base("/downloads/disk2/Rick.and.Morty/", BASE) == "/downloads/disk2/Rick.and.Morty"
    assert folder_in_base("/downloads/disk2/Rick et Morty/Saison 09", BASE) == "/downloads/disk2/Rick et Morty"
    assert folder_in_base("/downloads/disk2", BASE) is None
    assert folder_in_base("/downloads/disk22/Foo", BASE) is None
    assert folder_in_base("/downloads/disk1/Foo", BASE) is None


def test_new_series_folder_is_identified_by_jellyfin():
    assert new_series_folder(BASE + "/", RICK) == "/downloads/disk2/Rick et Morty (2013) [tmdbid-60625]"
    odd = RICK.model_copy(update={"title": "Star Wars : Andor", "year": "../x"})
    assert new_series_folder(BASE, odd) == "/downloads/disk2/Star Wars - Andor [tmdbid-60625]"


async def test_jellyfin_folder_wins_and_the_fullest_copy_is_kept():
    # Jellyfin knows two folders for the same show (seen in production): keep the fuller one.
    jelly = FakeJellyfin({60625: [("/media/disk2/Rick et Morty", 10), ("/media/disk2/Rick.and.Morty", 81)]})
    assert await find_series_folder(RICK, BASE, jelly, FakeTransmission()) == "/downloads/disk2/Rick.and.Morty"


async def test_transmission_folder_when_jellyfin_does_not_know_it_yet():
    torrents = [
        _torrent("Rick.and.Morty.S06.MULTI.1080p.WEB.MAX.H265.EAC3-Amen", "/downloads/disk2/Rick.and.Morty/"),
        _torrent("Rick.and.Morty.S07.MULTI.1080p.WEB.MAX.H265.EAC3-Amen", "/downloads/disk2/Rick.and.Morty/", 2),
        _torrent("Rick.and.Morty.S01.MULTI.1080p-GRP", "/downloads/disk2", 3),  # pack at the root: no series folder
        _torrent("Other.Show.S01E01.1080p-GRP", "/downloads/disk2/Other.Show/Saison 01", 4),
    ]
    found = await find_series_folder(RICK, BASE, FakeJellyfin(error=True), FakeTransmission(torrents))
    assert found == "/downloads/disk2/Rick.and.Morty"


async def test_nothing_found_without_any_trace():
    assert await find_series_folder(RICK, BASE, None, FakeTransmission(error=True)) is None


async def test_series_folder_remembers_its_choice(tmp_path):
    lib = SeriesLibrary(tmp_path / "s.json")
    lib.add(RICK)
    jelly = FakeJellyfin({60625: [("/media/disk2/Rick.and.Morty", 81)]})
    assert await series_folder(lib.get(60625), BASE, jelly, FakeTransmission(), lib) == "/downloads/disk2/Rick.and.Morty"
    assert lib.get(60625).folder == "/downloads/disk2/Rick.and.Morty"
    # Next time the stored folder is used as is, even with Jellyfin down.
    assert await series_folder(lib.get(60625), BASE, FakeJellyfin(error=True), None, lib) == \
        "/downloads/disk2/Rick.and.Morty"


async def test_series_folder_new_show_gets_an_identified_folder(tmp_path):
    lib = SeriesLibrary(tmp_path / "s.json")
    lib.add(RICK)
    folder = await series_folder(lib.get(60625), BASE, FakeJellyfin(), FakeTransmission(), lib)
    assert folder == "/downloads/disk2/Rick et Morty (2013) [tmdbid-60625]"
    assert lib.get(60625).folder == folder


async def test_stored_folder_outside_the_tv_folder_is_found_again(tmp_path):
    lib = SeriesLibrary(tmp_path / "s.json")
    lib.add(RICK.model_copy(update={"folder": "/old/disk/Rick.and.Morty"}))
    jelly = FakeJellyfin({60625: [("/media/disk2/Rick.and.Morty", 81)]})
    assert await series_folder(lib.get(60625), BASE, jelly, None, lib) == "/downloads/disk2/Rick.and.Morty"


async def test_no_tv_folder_means_transmission_default():
    assert await series_folder(RICK, None, FakeJellyfin(), FakeTransmission(), None) is None
