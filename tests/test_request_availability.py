from __future__ import annotations

from torsearch.config import Config, NotificationChannel
from torsearch.monitor.runner import run_request_availability
from torsearch.requests.store import RequestStatus, RequestStore


class FakeJellyfin:
    enabled = True

    def __init__(self, owned):
        self._owned = owned

    async def owned(self):
        return dict(self._owned)


class FakeNotifier:
    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    async def notify_message(self, channels, title, body):
        self.messages.append((title, body))


async def test_approved_request_becomes_available_and_notifies(tmp_path):
    store = RequestStore(tmp_path / "requests.json")
    movie = store.add("bob", "movie", 603, "The Matrix", "1999", None)
    store.set_status(movie.id, RequestStatus.APPROVED, "admin")
    pending = store.add("ann", "tv", 1399, "GoT", "2011", None)  # not approved: ignored
    other = store.add("eve", "movie", 7, "Absent", None, None)
    store.set_status(other.id, RequestStatus.APPROVED, "admin")
    notifier = FakeNotifier()
    cfg = Config(notifications=[NotificationChannel(name="n", type="ntfy", url="http://n")])

    done = await run_request_availability(
        store, FakeJellyfin({"movie:603": "a", "tv:1399": "b"}), notifier, cfg,
    )
    assert [r.id for r in done] == [movie.id]
    assert store.get(movie.id).status == RequestStatus.AVAILABLE
    assert store.get(movie.id).available_at is not None
    assert store.get(pending.id).status == RequestStatus.PENDING
    assert store.get(other.id).status == RequestStatus.APPROVED
    assert notifier.messages == [("TorrSearch - demandes", "Disponible : The Matrix (demande de bob)")]

    again = await run_request_availability(store, FakeJellyfin({"movie:603": "a"}), notifier, cfg)
    assert again == []
    assert len(notifier.messages) == 1


async def test_without_jellyfin_nothing_changes(tmp_path):
    store = RequestStore(tmp_path / "requests.json")
    r = store.add("bob", "movie", 603, "The Matrix", "1999", None)
    store.set_status(r.id, RequestStatus.APPROVED, "admin")
    assert await run_request_availability(store, None, FakeNotifier(), Config()) == []
