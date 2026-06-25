from torsearch.requests.store import MediaRequest, RequestStatus, RequestStore


def _store(tmp_path):
    return RequestStore(tmp_path / "requests.json")


def test_add_creates_pending(tmp_path):
    s = _store(tmp_path)
    r = s.add("bob", "movie", 603, "The Matrix", "1999", "/p.jpg")
    assert isinstance(r, MediaRequest)
    assert r.status == RequestStatus.PENDING
    assert r.username == "bob" and r.tmdb_id == 603
    assert s.count_pending() == 1


def test_add_dedupes_pending_same_title(tmp_path):
    s = _store(tmp_path)
    first = s.add("bob", "movie", 603, "The Matrix", "1999", None)
    again = s.add("alice", "movie", 603, "The Matrix", "1999", None)
    assert again.id == first.id  # already pending -> same request
    assert s.count_pending() == 1


def test_pending_excludes_decided(tmp_path):
    s = _store(tmp_path)
    r = s.add("bob", "tv", 1399, "GoT", "2011", None)
    s.set_status(r.id, RequestStatus.APPROVED, "admin")
    assert s.count_pending() == 0
    assert s.pending() == []
    # a fresh request for the same title is allowed again after decision
    r2 = s.add("bob", "tv", 1399, "GoT", "2011", None)
    assert r2.id != r.id
    assert s.count_pending() == 1


def test_set_status_records_decision(tmp_path):
    s = _store(tmp_path)
    r = s.add("bob", "movie", 1, "X", None, None)
    updated = s.set_status(r.id, RequestStatus.REJECTED, "admin")
    assert updated.status == RequestStatus.REJECTED
    assert updated.decided_by == "admin"
    assert updated.decided_at is not None


def test_set_status_unknown_id_returns_none(tmp_path):
    s = _store(tmp_path)
    assert s.set_status("nope", RequestStatus.APPROVED, "admin") is None


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "requests.json"
    rid = RequestStore(path).add("bob", "movie", 5, "Y", None, None).id
    assert RequestStore(path).get(rid).username == "bob"
    assert not path.with_name(path.name + ".tmp").exists()


def test_for_user_returns_only_that_user_newest_first(tmp_path):
    s = _store(tmp_path)
    s.add("bob", "movie", 1, "A", None, None)
    s.add("alice", "movie", 2, "B", None, None)
    s.add("bob", "tv", 3, "C", None, None)
    assert [r.title for r in s.for_user("bob")] == ["C", "A"]
    assert [r.title for r in s.for_user("alice")] == ["B"]
