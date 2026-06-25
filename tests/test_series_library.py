from datetime import UTC, datetime

from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedSeries

NOW = datetime(2026, 6, 21, tzinfo=UTC)


def _series(tmdb_id=1, title="Show"):
    return WantedSeries(tmdb_id=tmdb_id, title=title, year="2024", added_at=NOW)


def test_add_and_list_persists(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    assert lib.add(_series()) is True
    assert [s.title for s in SeriesLibrary(tmp_path / "series.json").list()] == ["Show"]


def test_add_dedupes(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series())
    assert lib.add(_series(title="Show bis")) is False
    assert len(lib.list()) == 1


def test_remove(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series(1))
    lib.add(_series(2, "Other"))
    lib.remove(1)
    assert [s.tmdb_id for s in lib.list()] == [2]


def test_mark_grabbed_unions_keys(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series(1))
    lib.mark_grabbed(1, ["S01E01", "S01E02"])
    lib.mark_grabbed(1, ["S01E02", "S01E03"])
    assert lib.list()[0].grabbed == ["S01E01", "S01E02", "S01E03"]
