import asyncio
import contextlib
import threading
import time
from types import SimpleNamespace

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TorrentInfo, TransmissionClient


class FakeRpc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.added = []

    def add_torrent(self, url, download_dir=None, timeout=None):
        self.added.append(url)
        self.last_download_dir = download_dir
        self.last_timeout = timeout
        return SimpleNamespace(id=42)


async def test_add_returns_torrent_id_and_passes_url():
    created = {}

    def factory(**kwargs):
        client = FakeRpc(**kwargs)
        created["client"] = client
        return client

    cfg = TransmissionConfig(host="tr.local", port=9092, username="u", password="p")
    tc = TransmissionClient(cfg, client_factory=factory)
    torrent_id = await tc.add("magnet:?xt=urn:btih:XYZ")

    assert torrent_id == 42
    assert created["client"].added == ["magnet:?xt=urn:btih:XYZ"]
    assert created["client"].kwargs["host"] == "tr.local"
    assert created["client"].kwargs["port"] == 9092
    assert created["client"].kwargs["protocol"] == "http"


async def test_add_passes_download_dir():
    captured = {}

    def factory(**kwargs):
        captured["client"] = FakeRpc(**kwargs)
        return captured["client"]

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    await tc.add("magnet:?xt=urn:btih:A", download_dir="/data/films")
    assert captured["client"].last_download_dir == "/data/films"

    await tc.add("magnet:?xt=urn:btih:B")
    assert captured["client"].last_download_dir is None


async def test_https_config_uses_https_protocol():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    await TransmissionClient(TransmissionConfig(https=True), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["protocol"] == "https"


async def test_empty_credentials_become_none():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    await TransmissionClient(TransmissionConfig(), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["username"] is None
    assert captured["password"] is None


async def test_client_created_once_with_short_timeout():
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return FakeRpc(**kwargs)

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    await tc.add("magnet:?xt=urn:btih:A")
    await tc.add("magnet:?xt=urn:btih:B")
    assert len(created) == 1
    assert created[0]["timeout"] == 10.0


def _fake_torrent(**o):
    base = dict(id=1, name="ubuntu.iso", progress=42.5, status="downloading",
                rate_download=1000, rate_upload=50, total_size=2000)
    base.update(o)
    return SimpleNamespace(**base)


class FakeRpcFull:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.torrents = [
            _fake_torrent(id=1, name="A"),
            _fake_torrent(id=2, name="B", progress=100.0, status="seeding"),
        ]
        self.calls = []

    def get_torrents(self):
        return self.torrents

    def stop_torrent(self, tid):
        self.calls.append(("stop", tid))

    def start_torrent(self, tid):
        self.calls.append(("start", tid))

    def remove_torrent(self, tid, delete_data=False):
        self.calls.append(("remove", tid, delete_data))


def _client_with(rpc):
    return TransmissionClient(TransmissionConfig(), client_factory=lambda **k: rpc)


async def test_list_torrents_maps_fields():
    infos = await _client_with(FakeRpcFull()).list_torrents()
    assert [i.name for i in infos] == ["A", "B"]
    a = infos[0]
    assert isinstance(a, TorrentInfo)
    assert a.id == 1 and a.percent == 42.5 and a.status == "downloading"
    assert a.down_rate == 1000 and a.up_rate == 50 and a.size == 2000


async def test_pause_calls_stop_torrent():
    rpc = FakeRpcFull()
    await _client_with(rpc).pause(7)
    assert ("stop", 7) in rpc.calls


async def test_resume_calls_start_torrent():
    rpc = FakeRpcFull()
    await _client_with(rpc).resume(7)
    assert ("start", 7) in rpc.calls


async def test_remove_calls_remove_torrent_without_data():
    rpc = FakeRpcFull()
    await _client_with(rpc).remove(7)
    assert ("remove", 7, False) in rpc.calls


async def test_rpc_does_not_block_the_event_loop():
    class SlowRpc(FakeRpcFull):
        def get_torrents(self):
            time.sleep(0.3)  # blocking I/O, like the real transmission-rpc client
            return self.torrents

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    infos = await _client_with(SlowRpc()).list_torrents()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert [i.name for i in infos] == ["A", "B"]
    assert ticks >= 10  # the loop kept running while the RPC was in flight


async def test_add_gets_a_longer_timeout_than_other_calls():
    # Adding by URL: Transmission answers only after fetching the .torrent itself.
    rpc = FakeRpc()
    await TransmissionClient(TransmissionConfig(), client_factory=lambda **k: rpc).add("https://t/x.torrent")
    assert rpc.last_timeout == 60.0


async def test_handshake_runs_off_the_event_loop_thread():
    seen = {}

    def factory(**kwargs):
        seen["thread"] = threading.get_ident()
        return FakeRpc(**kwargs)

    await TransmissionClient(TransmissionConfig(), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert seen["thread"] != threading.get_ident()


async def test_failed_handshake_is_retried_on_next_call():
    attempts = []

    def factory(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise ConnectionError("down")
        return FakeRpc(**kwargs)

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    with contextlib.suppress(ConnectionError):
        await tc.add("magnet:?xt=urn:btih:A")
    assert await tc.add("magnet:?xt=urn:btih:A") == 42
    assert len(attempts) == 2


async def test_calls_do_not_queue_behind_a_dead_host():
    def factory(**kwargs):
        time.sleep(0.3)  # handshake timing out against an unreachable host
        raise ConnectionError("down")

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    start = time.monotonic()
    results = await asyncio.gather(*(tc.list_torrents() for _ in range(4)), return_exceptions=True)
    assert all(isinstance(r, ConnectionError) for r in results)
    assert time.monotonic() - start < 0.6  # in parallel (~0.3 s), not one after another (~1.2 s)


class FakeRpcSession(FakeRpcFull):
    def get_session(self):
        return SimpleNamespace(version="4.0.6 (38c164933e)")

    def session_stats(self):
        return SimpleNamespace(torrent_count=12)


async def test_test_reports_version_and_torrent_count():
    assert await _client_with(FakeRpcSession()).test() == (True, "v4.0.6 · 12 torrents")


async def test_test_never_raises_and_masks_credentials():
    def factory(**kwargs):
        raise RuntimeError("Invalid URL 'http://u:TR-SECRET@:9091/transmission/rpc'")

    ok, message = await TransmissionClient(TransmissionConfig(), client_factory=factory).test()
    assert ok is False
    assert "TR-SECRET" not in message
