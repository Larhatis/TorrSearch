from datetime import UTC, datetime

from torsearch.library.movies import MovieLibrary
from torsearch.models import WantedMovie

NOW = datetime(2026, 6, 20, tzinfo=UTC)


def _movie(tmdb_id=1, title="Dune"):
    return WantedMovie(tmdb_id=tmdb_id, title=title, year="2024", added_at=NOW)


def test_add_and_list_persists(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    assert lib.add(_movie()) is True
    assert [m.title for m in MovieLibrary(tmp_path / "lib.json").list()] == ["Dune"]


def test_add_dedupes_by_tmdb_id(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie())
    assert lib.add(_movie(title="Dune bis")) is False
    assert len(lib.list()) == 1


def test_remove(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie(1))
    lib.add(_movie(2, "Other"))
    lib.remove(1)
    assert [m.tmdb_id for m in lib.list()] == [2]


def test_wanted_excludes_grabbed_and_mark_grabbed(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie(1))
    lib.mark_grabbed(1, "Dune.2024.1080p", NOW)
    assert lib.wanted() == []
    grabbed = lib.list()[0]
    assert grabbed.status == "grabbed"
    assert grabbed.grabbed_title == "Dune.2024.1080p"
    assert grabbed.grabbed_at == NOW
