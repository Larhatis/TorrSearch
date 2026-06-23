from types import SimpleNamespace

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TransmissionClient


class FakeRpc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.added = []

    def add_torrent(self, url, download_dir=None):
        self.added.append(url)
        self.last_download_dir = download_dir
        return SimpleNamespace(id=42)


def test_add_returns_torrent_id_and_passes_url():
    created = {}

    def factory(**kwargs):
        client = FakeRpc(**kwargs)
        created["client"] = client
        return client

    cfg = TransmissionConfig(host="tr.local", port=9092, username="u", password="p")
    tc = TransmissionClient(cfg, client_factory=factory)
    torrent_id = tc.add("magnet:?xt=urn:btih:XYZ")

    assert torrent_id == 42
    assert created["client"].added == ["magnet:?xt=urn:btih:XYZ"]
    assert created["client"].kwargs["host"] == "tr.local"
    assert created["client"].kwargs["port"] == 9092
    assert created["client"].kwargs["protocol"] == "http"


def test_add_passes_download_dir():
    captured = {}

    def factory(**kwargs):
        captured["client"] = FakeRpc(**kwargs)
        return captured["client"]

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    tc.add("magnet:?xt=urn:btih:A", download_dir="/data/films")
    assert captured["client"].last_download_dir == "/data/films"

    tc.add("magnet:?xt=urn:btih:B")
    assert captured["client"].last_download_dir is None


def test_https_config_uses_https_protocol():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    cfg = TransmissionConfig(https=True)
    TransmissionClient(cfg, client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["protocol"] == "https"


def test_empty_credentials_become_none():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    TransmissionClient(TransmissionConfig(), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["username"] is None
    assert captured["password"] is None


from torsearch.transmission.client import TorrentInfo


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


def test_list_torrents_maps_fields():
    infos = _client_with(FakeRpcFull()).list_torrents()
    assert [i.name for i in infos] == ["A", "B"]
    a = infos[0]
    assert isinstance(a, TorrentInfo)
    assert a.id == 1 and a.percent == 42.5 and a.status == "downloading"
    assert a.down_rate == 1000 and a.up_rate == 50 and a.size == 2000


def test_pause_calls_stop_torrent():
    rpc = FakeRpcFull()
    _client_with(rpc).pause(7)
    assert ("stop", 7) in rpc.calls


def test_resume_calls_start_torrent():
    rpc = FakeRpcFull()
    _client_with(rpc).resume(7)
    assert ("start", 7) in rpc.calls


def test_remove_calls_remove_torrent_without_data():
    rpc = FakeRpcFull()
    _client_with(rpc).remove(7)
    assert ("remove", 7, False) in rpc.calls
