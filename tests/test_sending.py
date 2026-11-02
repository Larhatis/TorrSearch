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
