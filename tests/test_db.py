from torsearch.db.database import Database


def _coll(tmp_path, name="things"):
    return Database(tmp_path / "t.db").collection(name)


def test_upsert_and_get_roundtrip(tmp_path):
    c = _coll(tmp_path)
    c.upsert("a", {"n": 1, "label": "x"})
    assert c.get("a") == {"n": 1, "label": "x"}
    assert c.get("missing") is None


def test_all_preserves_insertion_order(tmp_path):
    c = _coll(tmp_path)
    for i in range(3):
        c.upsert(f"id{i}", {"n": i})
    assert [d["n"] for d in c.all()] == [0, 1, 2]


def test_upsert_updates_in_place_keeping_order(tmp_path):
    c = _coll(tmp_path)
    c.upsert("a", {"n": 1})
    c.upsert("b", {"n": 2})
    c.upsert("a", {"n": 99})  # update existing -> stays first
    assert [d["n"] for d in c.all()] == [99, 2]


def test_delete_and_count(tmp_path):
    c = _coll(tmp_path)
    c.upsert("a", {})
    c.upsert("b", {})
    assert c.count() == 2 and c.is_empty() is False
    c.delete("a")
    assert c.count() == 1
    assert c.get("a") is None


def test_replace_all(tmp_path):
    c = _coll(tmp_path)
    c.upsert("old", {"n": 0})
    c.replace_all([("x", {"n": 1}), ("y", {"n": 2})])
    assert [d["n"] for d in c.all()] == [1, 2]
    assert c.get("old") is None


def test_collections_are_isolated(tmp_path):
    db = Database(tmp_path / "t.db")
    db.collection("a").upsert("1", {"v": "a"})
    db.collection("b").upsert("1", {"v": "b"})
    assert db.collection("a").get("1") == {"v": "a"}
    assert db.collection("b").get("1") == {"v": "b"}


def test_persists_across_instances(tmp_path):
    Database(tmp_path / "t.db").collection("c").upsert("k", {"v": 7})
    assert Database(tmp_path / "t.db").collection("c").get("k") == {"v": 7}


def test_wal_mode_enabled(tmp_path):
    import sqlite3
    Database(tmp_path / "t.db")
    con = sqlite3.connect(tmp_path / "t.db")
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert mode.lower() == "wal"
