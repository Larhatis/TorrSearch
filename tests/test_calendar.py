from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from torsearch.context import AppContext
from torsearch.library.calendar import build_calendar
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import EpisodeInfo, SeasonInfo, WantedMovie, WantedSeries
from torsearch.settings.store import SettingsStore
from torsearch.web.calendar_routes import day_label
from torsearch.web.routes import create_app

TODAY = date(2026, 10, 29)


def _ep(code_s, code_e, air):
    return EpisodeInfo(season_number=code_s, episode_number=code_e,
                       code=f"S{code_s:02d}E{code_e:02d}", name=f"Ep {code_e}", air_date=air)


class FakeTmdb:
    enabled = True

    async def seasons(self, tv_id):
        return [SeasonInfo(season_number=1, episodes=[
            _ep(1, 1, "2026-10-01"),   # too old: out of range
            _ep(1, 2, "2026-10-27"),   # aired, grabbed
            _ep(1, 3, "2026-10-28"),   # aired, missing
            _ep(1, 4, "2026-11-04"),   # upcoming
            _ep(1, 5, None),
        ])]

    async def release_date(self, movie_id):
        return ("2026-11-15", "numerique")


def _series():
    return WantedSeries(tmdb_id=1, title="Severance", added_at=datetime.now(UTC), grabbed=["S01E02"])


def _movie():
    return WantedMovie(tmdb_id=2, title="Dune", added_at=datetime.now(UTC))


async def test_build_calendar_groups_by_day_with_status():
    days = await build_calendar(FakeTmdb(), [_series()], [_movie()], TODAY)
    flat = [(d.isoformat(), e.detail, e.status) for d, entries in days for e in entries]
    assert flat == [
        ("2026-10-27", "S01E02 · Ep 2", "acquired"),
        ("2026-10-28", "S01E03 · Ep 3", "missing"),
        ("2026-11-04", "S01E04 · Ep 4", "upcoming"),
        ("2026-11-15", "Sortie numerique", "upcoming"),
    ]


async def test_build_calendar_without_tmdb_is_empty():
    class Off:
        enabled = False

    assert await build_calendar(Off(), [_series()], [_movie()], TODAY) == []


def test_day_label():
    assert day_label(TODAY, TODAY).startswith("Aujourd'hui")
    assert day_label(date(2026, 10, 30), TODAY) == "Demain · Vendredi 30 octobre"


def test_calendar_page_renders(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    ctx._tmdb = FakeTmdb()
    series = SeriesLibrary(tmp_path / "series.json")
    series.add(WantedSeries(tmdb_id=1, title="Severance", added_at=datetime.now(UTC)))
    client = TestClient(create_app(ctx, series_library=series, library=MovieLibrary(tmp_path / "m.json")))
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert "A venir" in resp.text
    assert 'href="/calendar"' in resp.text
