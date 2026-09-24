from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from pydantic import BaseModel
from transmission_rpc import Client

from torsearch.config import TransmissionConfig
from torsearch.redact import redact

T = TypeVar("T")

DEFAULT_TIMEOUT = 10.0  # seconds per connect/read (transmission-rpc defaults to 30)
ADD_TIMEOUT = 60.0  # adding by URL: Transmission replies only once it has fetched the .torrent

# Dedicated pool: an unreachable Transmission can only tie up these threads, never the
# default executor that asyncio also uses for DNS lookups (searches, TMDB, Jellyfin).
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="transmission")


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

    Each RPC runs in a dedicated worker thread so a slow or unreachable Transmission never
    blocks the event loop. Connect/read waits are bounded by ``timeout`` (``ADD_TIMEOUT``
    when adding a torrent).
    """

    def __init__(self, config: TransmissionConfig, client_factory=Client, timeout: float = DEFAULT_TIMEOUT):
        self._config = config
        self._client_factory = client_factory
        self._timeout = timeout
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        client = self._client
        if client is None:
            # Creating the client is itself a network call (handshake): run it outside the
            # lock so callers never queue behind an unreachable host, and keep whichever
            # client wins the race. RPC calls themselves are not serialized either.
            client = self._client_factory(
                protocol="https" if self._config.https else "http",
                host=self._config.host,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
                timeout=self._timeout,
            )
            with self._lock:
                if self._client is None:
                    self._client = client
                client = self._client
        return client

    async def _run(self, fn: Callable[[Any], T]) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_EXECUTOR, lambda: fn(self._get_client()))

    async def add(self, download_url: str, download_dir: str | None = None) -> int:
        torrent = await self._run(
            lambda c: c.add_torrent(download_url, download_dir=download_dir, timeout=ADD_TIMEOUT)
        )
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

    async def test(self) -> tuple[bool, str]:
        """Connection check for the status panel: never raises, never echoes credentials."""
        try:
            version, count = await self._run(
                lambda c: (c.get_session().version, c.session_stats().torrent_count)
            )
        except Exception as exc:
            return False, redact(str(exc))
        label = str(version).split()[0] if version else "?"
        return True, f"v{label} · {count} torrent{'s' if count != 1 else ''}"
