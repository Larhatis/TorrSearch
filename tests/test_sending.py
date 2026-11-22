"""send_release: one path to Transmission for the web UI and for Claude (chantier 11)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from torsearch.config import Config, PathsConfig
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.sending import send_release
from torsearch.library.series import SeriesLibrary
from torsearch.models import Category, WantedMovie
from torsearch.monitor.grabs import GrabRegistry
from torsearch.monitor.history import MonitorHistory
from torsearch.transmission.client import AddedTorrent


class FakeTransmission:
    def __init__(self, answer=None, error=None):
        self._answer = answer if answer is not None else AddedTorrent(id=7, info_hash="hh")
        self._error = error
        self.added: list[tuple[str, str | None]] = []

    async def add(self, url, download_dir=None):
        if self._error:
            raise RuntimeError(self._error)
        self.added.append((url, download_dir))
        return self._answer


def _state(tmp_path, transmission):
    db = Database(tmp_path / "db.sqlite")
    movies = MovieLibrary(db)
    movies.add(WantedMovie(tmdb_id=1384216, title="The Dog Stars", year="2026", added_at=datetime.now(UTC)))
    ctx = SimpleNamespace(transmission=transmission,
                          config=Config(paths=PathsConfig(by_category={"movies": "/films"})))
    return SimpleNamespace(ctx=ctx, library=movies, series_library=SeriesLibrary(db), history=MonitorHistory(db),
                           grabs=GrabRegistry(db))


async def test_send_release_files_records_and_reports(tmp_path):
    tr = FakeTransmission()
    state = _state(tmp_path, tr)
    out = await send_release(state, "magnet:?x", "The.Dog.Stars.2026.MULTi.1080p.WEB-GRP", Category.MOVIES)
    assert out.ok and out.torrent_id == 7
    assert "Ajoute a Transmission (#7)" in out.message
    assert "marque acquis dans la surveillance (The Dog Stars)" in out.message
    assert tr.added == [("magnet:?x", "/films/The Dog Stars (2026) [tmdbid-1384216]")]
    assert state.grabs.get("hh").origin == "manual"
    assert state.library.get(1384216).status == "grabbed"


async def test_send_release_falls_back_to_the_result_hash(tmp_path):
    state = _state(tmp_path, FakeTransmission(AddedTorrent(id=3)))
    await send_release(state, "magnet:?x", "Some.Film.2020.1080p", Category.MOVIES, fallback_hash="FB")
    assert state.grabs.get("fb").origin == "manual"


async def test_send_release_transmission_error_is_redacted(tmp_path):
    state = _state(tmp_path, FakeTransmission(error="Invalid URL 'http://u:SECRET@host:9091/transmission/rpc'"))
    out = await send_release(state, "magnet:?x", "T", Category.MOVIES)
    assert not out.ok and out.torrent_id is None
    assert "SECRET" not in out.message and out.message.startswith("Erreur Transmission")
    assert state.grabs._c.count() == 0


class SpaceTransmission(FakeTransmission):
    def __init__(self, free):
        super().__init__()
        self.free = free

    async def free_space(self, path):
        return self.free


async def test_manual_send_warns_on_a_nearly_full_disk(tmp_path):
    out = await send_release(_state(tmp_path, SpaceTransmission(30_000_000_000)), "magnet:?x",
                             "Some.Film.2020.1080p", Category.MOVIES)
    assert out.ok  # never blocked
    assert "attention : disque presque plein (30 Go libres)" in out.message


async def test_manual_send_no_warning_with_room(tmp_path):
    out = await send_release(_state(tmp_path, SpaceTransmission(600_000_000_000)), "magnet:?x",
                             "Some.Film.2020.1080p", Category.MOVIES)
    assert "attention" not in out.message


async def test_send_release_of_a_followed_series_uses_its_folder(tmp_path):
    from torsearch.models import WantedSeries

    tr = FakeTransmission()
    state = _state(tmp_path, tr)
    state.ctx.config = Config(paths=PathsConfig(by_category={"tv": "/downloads/disk2"}))
    state.series_library.add(WantedSeries(tmdb_id=60625, title="Rick et Morty", original_title="Rick and Morty",
                                          year="2013", added_at=datetime.now(UTC),
                                          folder="/downloads/disk2/Rick.and.Morty"))
    await send_release(state, "magnet:?x", "Rick.and.Morty.S09E01.MULTi.1080p.WEB-GRP", Category.TV)
    assert tr.added == [("magnet:?x", "/downloads/disk2/Rick.and.Morty/Saison 09")]


async def test_send_release_of_an_unfollowed_series_reuses_its_jellyfin_folder(tmp_path):
    # Nobody follows Squid Game: season 3 must join the folder Jellyfin already shows,
    # not start "Squid Game/" (a second series in Jellyfin).
    from torsearch.jellyfin.client import JellyfinSeries

    class Jelly:
        enabled = True

        async def series_list(self):
            return [JellyfinSeries("93405", "Squid Game", None, 2021,
                                   "/media/disk2/Squid.Game.S02.MULTi.1080p.WEB.H265-FW", 7)]

    tr = FakeTransmission()
    state = _state(tmp_path, tr)
    state.ctx.config = Config(paths=PathsConfig(by_category={"tv": "/downloads/disk2"}))
    state.ctx.jellyfin = Jelly()
    await send_release(state, "magnet:?x", "Squid.Game.S03E01.MULTi.1080p.WEB-GRP", Category.TV)
    assert tr.added == [("magnet:?x", "/downloads/disk2/Squid.Game.S02.MULTi.1080p.WEB.H265-FW/Saison 03")]


async def test_send_release_of_an_unknown_series_keeps_the_title_folder(tmp_path):
    tr = FakeTransmission()
    state = _state(tmp_path, tr)
    state.ctx.config = Config(paths=PathsConfig(by_category={"tv": "/downloads/disk2"}))
    await send_release(state, "magnet:?x", "Brand.New.Show.S01E01.MULTi.1080p.WEB-GRP", Category.TV)
    assert tr.added == [("magnet:?x", "/downloads/disk2/Brand New Show/Saison 01")]
