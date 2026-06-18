from types import SimpleNamespace

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TransmissionClient


class FakeRpc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.added = []

    def add_torrent(self, url):
        self.added.append(url)
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
