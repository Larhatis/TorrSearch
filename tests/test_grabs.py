from datetime import UTC, datetime

from torsearch.monitor.grabs import GrabRegistry, added_hash
from torsearch.monitor.history import MonitorRecord
from torsearch.transmission.client import AddedTorrent


def _rec(kind="grabbed", infohash=None, source="c411", title="Some.Release.1080p"):
    return MonitorRecord(search="s", title=title, source=source, infohash=infohash,
                         download_url="magnet:?xt=urn:btih:x", kind=kind, at=datetime(2026, 10, 1, tzinfo=UTC))


def test_record_and_is_auto_ignore_case(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    g.record("ABC", "T", "auto", "movie:1")
    assert g.is_auto("abc")
    assert g.get("Abc").target == "movie:1"


def test_empty_hash_is_not_recorded(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    g.record("", "T", "auto")
    g.record(None, "T", "auto")
    assert g.is_auto("") is False
    assert g.is_auto(None) is False


def test_manual_entry_is_never_turned_auto(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    g.record("aa", "T", "manual")
    g.record("aa", "T", "auto")
    g.record("bb", "T", "auto")
    g.record("bb", "T", "manual")
    assert g.is_auto("aa") is False
    assert g.is_auto("bb") is False


def test_forget(tmp_path):
    g = GrabRegistry(tmp_path / "g.db")
    g.record("aa", "T", "auto")
    g.forget("AA")
    assert g.get("aa") is None


def test_seed_from_history_only_auto_grabs_with_hash(tmp_path):
    recs = [_rec(infohash="H1"), _rec(infohash="H2", source="manuel"), _rec(infohash=None),
            _rec(kind="found", infohash="H3")]
    g = GrabRegistry(tmp_path / "g.db")
    assert g.seed_from_history(recs) == 1
    assert g.is_auto("h1")
    assert not g.is_auto("h2") and not g.is_auto("h3")
    assert g.seed_from_history([_rec(infohash="H9")]) == 0  # registry not empty: no second seeding
    assert not g.is_auto("h9")


def test_added_hash():
    assert added_hash(AddedTorrent(id=1, info_hash="FF")) == "ff"
    assert added_hash(1) == ""
    assert added_hash(None) == ""
