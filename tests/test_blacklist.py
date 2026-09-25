from __future__ import annotations

from pathlib import Path

from torsearch.db.database import Database
from torsearch.library.blacklist import Blacklist


def test_blacklist_add_and_check(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    bl = Blacklist(db)

    assert not bl.is_blacklisted("abc123hash", "Movie.2024.1080p")

    bl.add("ABC123hash", "Movie.2024.1080p", reason="stalled")

    # Infohash check is case-insensitive
    assert bl.is_blacklisted("abc123hash", "Other.Title")
    assert bl.is_blacklisted("ABC123HASH", "Other.Title")

    # Title match also works
    assert bl.is_blacklisted(None, "Movie.2024.1080p")
    assert not bl.is_blacklisted(None, "Different.Movie")


def test_blacklist_remove_and_list(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    bl = Blacklist(db)

    bl.add("hash1", "Movie1", reason="failed")
    bl.add("hash2", "Movie2", reason="unwanted")

    items = bl.list()
    assert len(items) == 2
    assert {i.infohash for i in items} == {"hash1", "hash2"}

    bl.remove("hash1")
    assert not bl.is_blacklisted("hash1", "Movie1")
    assert len(bl.list()) == 1
