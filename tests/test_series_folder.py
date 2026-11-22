"""A followed series is filed in the folder where it already lives (Jellyfin, Transmission)."""
from __future__ import annotations

from datetime import UTC, datetime

from torsearch.jellyfin.client import JellyfinSeries
from torsearch.library.series import SeriesLibrary
from torsearch.library.series_folder import (
    FolderChoice,
    choose_series_folder,
    find_release_folder,
    find_series_folder,
    folder_in_base,
    map_library_path,
    new_series_folder,
    remember_folder,
)
from torsearch.models import WantedSeries
from torsearch.parser.release import parse_release
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


async def test_jellyfin_folder_is_chosen_and_worth_remembering(tmp_path):
    lib = SeriesLibrary(tmp_path / "s.json")
    lib.add(RICK)
    jelly = FakeJellyfin({60625: [("/media/disk2/Rick.and.Morty", 81)]})
    choice = await choose_series_folder(lib.get(60625), BASE, jelly, FakeTransmission())
    assert choice == FolderChoice("/downloads/disk2/Rick.and.Morty", remember=True)
    remember_folder(lib, lib.get(60625), choice)
    assert lib.get(60625).folder == "/downloads/disk2/Rick.and.Morty"
    # Jellyfin down next time: the remembered folder is used.
    choice = await choose_series_folder(lib.get(60625), BASE, FakeJellyfin(error=True), None)
    assert choice.path == "/downloads/disk2/Rick.and.Morty"


async def test_jellyfin_wins_over_a_remembered_folder_renamed_by_hand():
    old = RICK.model_copy(update={"folder": "/downloads/disk2/Rick et Morty"})
    jelly = FakeJellyfin({60625: [("/media/disk2/Rick.and.Morty", 91)]})
    assert (await choose_series_folder(old, BASE, jelly, None)).path == "/downloads/disk2/Rick.and.Morty"


async def test_an_outage_never_pins_a_new_folder():
    # Jellyfin unreachable and no torrent left: a fallback folder is used for this send,
    # but not remembered (it would duplicate the show for good).
    choice = await choose_series_folder(RICK, BASE, FakeJellyfin(error=True), FakeTransmission(error=True))
    assert choice == FolderChoice("/downloads/disk2/Rick et Morty (2013) [tmdbid-60625]", remember=False)


async def test_new_show_gets_an_identified_folder_remembered_when_jellyfin_answered():
    choice = await choose_series_folder(RICK, BASE, FakeJellyfin(), FakeTransmission())
    assert choice == FolderChoice("/downloads/disk2/Rick et Morty (2013) [tmdbid-60625]", remember=True)


async def test_show_with_history_keeps_the_old_title_folder():
    # Followed before v0.12.2: its episodes went to "Title/"; never start a second folder.
    old = RICK.model_copy(update={"grabbed": ["S09E01"]})
    choice = await choose_series_folder(old, BASE, FakeJellyfin(), FakeTransmission())
    assert choice.path == "/downloads/disk2/Rick et Morty"


async def test_transmission_folder_is_not_remembered():
    torrents = [_torrent("Rick.and.Morty.S06.MULTI.1080p-Amen", "/downloads/disk2/Rick.and.Morty/")]
    choice = await choose_series_folder(RICK, BASE, FakeJellyfin(), FakeTransmission(torrents))
    assert choice == FolderChoice("/downloads/disk2/Rick.and.Morty", remember=False)


async def test_transmission_ignores_a_folder_named_after_another_show():
    office = WantedSeries(tmdb_id=2316, title="The Office", year="2005", added_at=NOW)
    torrents = [_torrent("The.Office.S01E01.1080p-GRP", "/downloads/disk2/Le Bureau/Saison 01")]
    assert await find_series_folder(office, BASE, None, FakeTransmission(torrents)) is None


async def test_remembered_folder_outside_the_tv_folder_is_ignored():
    old = RICK.model_copy(update={"folder": "/old/disk/Rick.and.Morty"})
    assert (await choose_series_folder(old, BASE, FakeJellyfin(), None)).path.endswith("[tmdbid-60625]")


async def test_no_tv_folder_means_transmission_default():
    assert await choose_series_folder(RICK, None, FakeJellyfin(), FakeTransmission()) is None


def test_dot_dot_never_escapes_the_tv_folder():
    assert map_library_path("/media/disk2/..", BASE) is None
    assert folder_in_base("/downloads/disk2/../etc/x", BASE) is None


def test_same_mount_in_both_containers():
    assert map_library_path("/tv/Show", "/tv") == "/tv/Show"


# --- Releases of shows that are not followed (manual sends, free searches) ---------------

class FakeJellyfinShows:
    enabled = True

    def __init__(self, shows=None, error=False):
        self._shows = shows or []
        self._error = error

    async def series_list(self):
        if self._error:
            raise RuntimeError("down")
        return list(self._shows)


def _show(name, path, tmdb="1", year=None, original=None, episodes=0):
    return JellyfinSeries(tmdb_id=tmdb, name=name, original_title=original, year=year, path=path, episodes=episodes)


LIBRARY = [
    _show("Squid Game", "/media/disk2/Squid.Game.S02.MULTi.1080p.WEB.H265-FW", "93405", 2021, episodes=7),
    _show("Dexter", "/media/disk2/Dexter.COMPLETE.MULTi.1080p", "1405", 2006, episodes=96),
    _show("Dexter: Original Sin", "/media/disk2/Dexter.Original.Sin.S01E01.MULTi", "219937", 2024, episodes=1),
    _show("Ça : Bienvenue à Derry", "/media/disk2/IT.Welcome.to.Derry.S01", "200875", 2025,
          original="IT: Welcome to Derry", episodes=8),
    _show("Tulsa King", "/media/disk2/Tulsa King", "153312", 2022, episodes=6),
    _show("Tulsa King", "/media/disk2/Tulsa.King", "153312", 2022, episodes=29),
]


async def test_unfollowed_show_goes_to_the_folder_jellyfin_knows():
    # The bug of Rick and Morty for a show nobody follows: S03 would start "Squid Game/".
    rel = parse_release("Squid.Game.S03E01.MULTi.1080p.WEB.H265-FW")
    folder = await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), None)
    assert folder == "/downloads/disk2/Squid.Game.S02.MULTi.1080p.WEB.H265-FW"


async def test_unfollowed_show_matches_the_original_title_and_the_fuller_copy():
    rel = parse_release("IT.Welcome.to.Derry.S02E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), None) == \
        "/downloads/disk2/IT.Welcome.to.Derry.S01"
    rel = parse_release("Tulsa.King.S04E07.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), None) == "/downloads/disk2/Tulsa.King"


async def test_unfollowed_show_never_lands_in_a_neighbouring_show():
    rel = parse_release("Dexter.Original.Sin.S02E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), None) == \
        "/downloads/disk2/Dexter.Original.Sin.S01E01.MULTi"
    rel = parse_release("Dexter.S09E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), None) == \
        "/downloads/disk2/Dexter.COMPLETE.MULTi.1080p"


async def test_two_shows_of_the_same_name_are_never_guessed():
    shows = [_show("Shogun", "/media/disk2/Shogun.1980", "100", 1980),
             _show("Shogun", "/media/disk2/Shogun", "126308", 2024)]
    rel = parse_release("Shogun.S02E01.MULTi.1080p-GRP")
    torrents = [_torrent("Shogun.S01E01.1080p-GRP", "/downloads/disk2/Shogun.1980/Saison 01")]
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(shows), FakeTransmission(torrents)) is None
    # The release year settles it.
    rel = parse_release("Shogun.2024.S02E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(shows), None) == "/downloads/disk2/Shogun"


async def test_unfollowed_show_falls_back_to_transmission():
    torrents = [_torrent("Paolo.S01E01.FRENCH.1080p.WEB.H265-GL0P.mkv", "/downloads/disk2/Paolo/Saison 01")]
    rel = parse_release("Paolo.S01E02.FRENCH.1080p.WEB.H265-GL0P")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(error=True), FakeTransmission(torrents)) == \
        "/downloads/disk2/Paolo"


async def test_unknown_unfollowed_show_keeps_the_default_folder():
    rel = parse_release("Brand.New.Show.S01E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(LIBRARY), FakeTransmission()) is None
    assert await find_release_folder(rel, None, FakeJellyfinShows(LIBRARY), None) is None
    assert await find_release_folder(parse_release("Squid.Game.2021.1080p"), BASE,  # no episode
                                     FakeJellyfinShows(LIBRARY), None) is None


async def test_jellyfin_folder_outside_the_tv_folder_is_ignored():
    shows = [_show("Squid Game", "/media/disk1/Anime/Squid.Game", "93405", 2021)]
    rel = parse_release("Squid.Game.S03E01.MULTi.1080p-GRP")
    assert await find_release_folder(rel, BASE, FakeJellyfinShows(shows), None) is None
