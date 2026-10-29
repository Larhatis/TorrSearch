from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from torsearch.config import Config, PathsConfig
from torsearch.db.database import Database
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


class FakeTransmission:
    def __init__(self, fail=False):
        self.dirs: list[str | None] = []
        self._fail = fail

    async def add(self, download_url, download_dir=None):
        if self._fail:
            raise RuntimeError("down")
        self.dirs.append(download_dir)
        return 7


class Ctx:
    def __init__(self, transmission):
        self.search_service = SearchService([])
        self.transmission = transmission
        self.config = Config(paths=PathsConfig(by_category={"movies": "/films", "tv": "/series"}))
        self.jellyfin = None
        self.tmdb = None


def _setup(tmp_path, fail=False):
    db = Database(tmp_path / "db.sqlite")
    movies, series, history = MovieLibrary(db), SeriesLibrary(db), MonitorHistory(db)
    movies.add(WantedMovie(tmdb_id=1384216, title="The Dog Stars", year="2026", added_at=datetime.now(UTC)))
    series.add(WantedSeries(tmdb_id=247718, title="MobLand", added_at=datetime.now(UTC)))
    tx = FakeTransmission(fail)
    client = TestClient(create_app(Ctx(tx), history=history, library=movies, series_library=series))
    return client, tx, movies, series, history


def _download(client, title, category="movies"):
    return client.post("/download", data={"download_url": "magnet:?x", "category": category, "title": title})


def test_manual_movie_download_is_filed_and_marked(tmp_path):
    client, tx, movies, _, history = _setup(tmp_path)
    resp = _download(client, "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip.x265-GL0P")
    assert tx.dirs == ["/films/The Dog Stars (2026) [tmdbid-1384216]"]
    assert movies.get(1384216).status == "grabbed"
    assert movies.get(1384216).grabbed_title == "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip.x265-GL0P"
    assert [r.kind for r in history.records()] == ["grabbed"]
    assert "surveillance" in resp.text


def test_manual_episode_download_is_filed_and_marked(tmp_path):
    client, tx, _, series, _ = _setup(tmp_path)
    _download(client, "MobLand.S02E03.MULTi.2160p.WEB-GRP", category="other")
    assert tx.dirs == ["/series/MobLand/Saison 02"]
    assert series.get(247718).grabbed == ["S02E03"]


def test_unwatched_movie_gets_a_folder_from_its_release_name(tmp_path):
    client, tx, movies, _, history = _setup(tmp_path)
    _download(client, "Heat.1995.MULTi.2160p.BluRay-QTZ")
    assert tx.dirs == ["/films/Heat (1995)"]
    assert history.records() == []


def test_failed_download_marks_nothing(tmp_path):
    client, _, movies, _, history = _setup(tmp_path, fail=True)
    _download(client, "The.Dog.Stars.2026.MULTi.VFQ.1080p.WEBRip.x265-GL0P")
    assert movies.get(1384216).status == "wanted"
    assert history.records() == []
