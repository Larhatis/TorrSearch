"""Contract tests against real ``transmission_rpc.Torrent`` objects (not SimpleNamespace fakes).

A torrent is built from the raw RPC fields exactly as Transmission sends them, so a renamed or
deprecated attribute in transmission-rpc (``date_added`` -> ``added_date``, ``hashString`` ->
``hash_string``) breaks these tests instead of production.
"""
from __future__ import annotations

import warnings
from datetime import UTC, datetime

from transmission_rpc import Torrent

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TransmissionClient

ADDED = 1761735000  # 2025-10-29 10:50:00 UTC

RPC_FIELDS = {
    "id": 42, "name": "MobLand.S01.MULTi.2160p.WEB-X", "addedDate": ADDED, "percentDone": 0.25,
    "hashString": "abcdef0123", "status": 4, "rateDownload": 1500, "rateUpload": 300,
    "totalSize": 18_700_000_000, "eta": 3600, "peersConnected": 7, "peersSendingToUs": 3,
    "errorString": "", "error": 0, "downloadDir": "/downloads/disk2/MobLand/Saison 01",
}


class Rpc:
    def __init__(self, torrents):
        self.torrents = torrents

    def get_torrents(self):
        return self.torrents

    def add_torrent(self, url, download_dir=None, timeout=None):
        return Torrent(fields={"id": 77, "name": "added", "hashString": "ff"})


def _client(torrents):
    rpc = Rpc(torrents)
    return TransmissionClient(TransmissionConfig(), client_factory=lambda **k: rpc)


async def test_every_field_is_read_from_a_real_torrent_without_deprecation():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        [info] = await _client([Torrent(fields=RPC_FIELDS)]).list_torrents()
    assert info.id == 42
    assert info.name == "MobLand.S01.MULTi.2160p.WEB-X"
    assert info.date_added == datetime.fromtimestamp(ADDED, tz=UTC)
    assert info.percent == 25.0
    assert info.status == "downloading"
    assert (info.down_rate, info.up_rate, info.size) == (1500, 300, 18_700_000_000)
    assert info.eta == 3600
    assert (info.peers_connected, info.peers_sending) == (7, 3)
    assert info.info_hash == "abcdef0123"
    assert (info.error_string, info.error_code) == ("", 0)
    assert info.download_dir == "/downloads/disk2/MobLand/Saison 01"


async def test_unknown_eta_and_tracker_error():
    fields = {**RPC_FIELDS, "eta": -1, "status": 0, "error": 2, "errorString": "invalid passkey"}
    [info] = await _client([Torrent(fields=fields)]).list_torrents()
    assert info.eta is None
    assert info.status == "stopped"
    assert (info.error_code, info.error_string) == (2, "invalid passkey")


async def test_missing_fields_never_break_the_listing():
    # transmission-rpc raises KeyError (not AttributeError) for a field Transmission did not send.
    [info] = await _client([Torrent(fields={"id": 1, "name": "partial", "hashString": "aa"})]).list_torrents()
    assert (info.id, info.name, info.info_hash) == (1, "partial", "aa")
    assert info.date_added is None and info.percent == 0.0 and info.eta is None


async def test_add_returns_the_real_torrent_id():
    assert await _client([]).add("magnet:?xt=urn:btih:ff", "/d") == 77
