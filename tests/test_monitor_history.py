from datetime import UTC, datetime

from torsearch.monitor.history import MonitorHistory, MonitorRecord


def _rec(search="s", title="T", infohash="H", url="magnet:?xt=urn:btih:H", kind="grabbed"):
    return MonitorRecord(search=search, title=title, source="src", infohash=infohash,
                         download_url=url, kind=kind, at=datetime(2024, 1, 1, tzinfo=UTC))


def test_records_empty_when_no_file(tmp_path):
    assert MonitorHistory(tmp_path / "none.json").records() == []


def test_add_and_records_most_recent_first(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(title="first", infohash="H1", url="u1"))
    h.add(_rec(title="second", infohash="H2", url="u2"))
    assert [r.title for r in h.records()] == ["second", "first"]


def test_seen_keys_per_search(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(search="a", infohash="HA", url="u1"))
    h.add(_rec(search="b", infohash="HB", url="u2"))
    assert h.seen_keys("a") == {"HA"}
    assert h.seen_keys("b") == {"HB"}
    assert h.seen_keys("none") == set()


def test_seen_keys_falls_back_to_url(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(search="a", infohash=None, url="http://x/t.torrent"))
    assert h.seen_keys("a") == {"http://x/t.torrent"}


def test_persistence_round_trip_and_atomic(tmp_path):
    path = tmp_path / "monitor.json"
    MonitorHistory(path).add(_rec())
    assert MonitorHistory(path).records()[0].title == "T"
    assert not path.with_name(path.name + ".tmp").exists()


def test_history_capped_to_max_records(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json", max_records=5)
    for i in range(8):
        h.add(_rec(title=f"t{i}", infohash=f"H{i}", url=f"u{i}"))
    titles = [r.title for r in h.records()]
    assert len(titles) == 5  # only the last 5 kept
    assert titles == ["t7", "t6", "t5", "t4", "t3"]  # most recent first, oldest dropped
