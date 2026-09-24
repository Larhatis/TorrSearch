from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from transmission_rpc import Client

from torsearch.config import TransmissionConfig

T = TypeVar("T")

DEFAULT_TIMEOUT = 10.0  # seconds (transmission-rpc defaults to 30)


class TorrentInfo(BaseModel):
    id: int
    name: str
    percent: float
    status: str
    down_rate: int
    up_rate: int
    size: int


class TransmissionClient:
    """Async facade over the blocking ``transmission_rpc`` client.

    Each RPC runs in a worker thread (``asyncio.to_thread``) so a slow or unreachable
    Transmission never blocks the event loop; every call is bounded by ``timeout``.
    """

    def __init__(self, config: TransmissionConfig, client_factory=Client, timeout: float = DEFAULT_TIMEOUT):
        self._config = config
        self._client_factory = client_factory
        self._timeout = timeout
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        # Creating the client already performs a network call: do it once, even when two
        # worker threads race for it. RPC calls themselves are not serialized.
        with self._lock:
            if self._client is None:
                self._client = self._client_factory(
                    protocol="https" if self._config.https else "http",
                    host=self._config.host,
                    port=self._config.port,
                    username=self._config.username or None,
                    password=self._config.password or None,
                    timeout=self._timeout,
                )
            return self._client

    async def _run(self, fn: Callable[[Any], T]) -> T:
        return await asyncio.to_thread(lambda: fn(self._get_client()))

    async def add(self, download_url: str, download_dir: str | None = None) -> int:
        torrent = await self._run(lambda c: c.add_torrent(download_url, download_dir=download_dir))
        return torrent.id

    async def list_torrents(self) -> list[TorrentInfo]:
        torrents = await self._run(lambda c: c.get_torrents())
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
            for t in torrents
        ]

    async def pause(self, torrent_id: int) -> None:
        await self._run(lambda c: c.stop_torrent(torrent_id))

    async def resume(self, torrent_id: int) -> None:
        await self._run(lambda c: c.start_torrent(torrent_id))

    async def remove(self, torrent_id: int) -> None:
        await self._run(lambda c: c.remove_torrent(torrent_id, delete_data=False))
