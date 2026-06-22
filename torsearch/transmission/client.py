from __future__ import annotations

from pydantic import BaseModel
from transmission_rpc import Client

from torsearch.config import TransmissionConfig


class TorrentInfo(BaseModel):
    id: int
    name: str
    percent: float
    status: str
    down_rate: int
    up_rate: int
    size: int


class TransmissionClient:
    def __init__(self, config: TransmissionConfig, client_factory=Client):
        self._config = config
        self._client_factory = client_factory
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory(
                protocol="https" if self._config.https else "http",
                host=self._config.host,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
            )
        return self._client

    def add(self, download_url: str, download_dir: str | None = None) -> int:
        torrent = self._get_client().add_torrent(download_url, download_dir=download_dir)
        return torrent.id

    def list_torrents(self) -> list[TorrentInfo]:
        return [
            TorrentInfo(
                id=t.id,
                name=t.name,
                percent=float(getattr(t, "progress", 0.0)),
                status=str(t.status),
                down_rate=int(getattr(t, "rate_download", 0)),
                up_rate=int(getattr(t, "rate_upload", 0)),
                size=int(getattr(t, "total_size", 0)),
            )
            for t in self._get_client().get_torrents()
        ]

    def pause(self, torrent_id: int) -> None:
        self._get_client().stop_torrent(torrent_id)

    def resume(self, torrent_id: int) -> None:
        self._get_client().start_torrent(torrent_id)

    def remove(self, torrent_id: int) -> None:
        self._get_client().remove_torrent(torrent_id, delete_data=False)
