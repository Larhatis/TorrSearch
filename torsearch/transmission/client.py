from __future__ import annotations

from transmission_rpc import Client

from torsearch.config import TransmissionConfig


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

    def add(self, download_url: str) -> int:
        torrent = self._get_client().add_torrent(download_url)
        return torrent.id
