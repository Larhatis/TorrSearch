from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from pydantic import BaseModel
from transmission_rpc import Client, TransmissionAuthError, TransmissionConnectError, TransmissionTimeoutError

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
    eta: int | None = None
    peers_connected: int = 0
    peers_sending: int = 0
    error_string: str = ""
    info_hash: str = ""

    @property
    def size_formatted(self) -> str:
        s = float(self.size)
        if s >= 1024**3:
            return f"{s / (1024**3):.2f} Go"
        if s >= 1024**2:
            return f"{s / (1024**2):.1f} Mo"
        if s >= 1024:
            return f"{s / 1024:.0f} Ko"
        return f"{int(s)} o"

    @property
    def down_rate_formatted(self) -> str:
        r = float(self.down_rate)
        if r >= 1024**2:
            return f"{r / (1024**2):.1f} Mo/s"
        if r >= 1024:
            return f"{r / 1024:.0f} Ko/s"
        return f"{int(r)} o/s"

    @property
    def up_rate_formatted(self) -> str:
        r = float(self.up_rate)
        if r >= 1024**2:
            return f"{r / (1024**2):.1f} Mo/s"
        if r >= 1024:
            return f"{r / 1024:.0f} Ko/s"
        return f"{int(r)} o/s"

    @property
    def eta_formatted(self) -> str:
        if self.status in ("seeding", "stopped", "seed pending"):
            return "Termine" if self.percent >= 100.0 else "--"
        if self.eta is None or self.eta < 0 or self.down_rate <= 0:
            return "--"
        seconds = self.eta
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            rem_sec = seconds % 60
            return f"{minutes}m {rem_sec}s" if rem_sec else f"{minutes}m"
        hours = minutes // 60
        rem_min = minutes % 60
        if hours < 24:
            return f"{hours}h {rem_min}m" if rem_min else f"{hours}h"
        days = hours // 24
        return f"{days}j"

    @property
    def status_label(self) -> str:
        s = self.status.lower()
        if "download" in s:
            return "Telechargement"
        if "seed" in s:
            return "Partage"
        if "stop" in s:
            return "En pause"
        if "check" in s:
            return "Verification"
        if "error" in s or self.error_string:
            return "Erreur"
        return self.status


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
        out: list[TorrentInfo] = []
        for t in torrents:
            eta_val = getattr(t, "eta", None)
            eta_sec: int | None = None
            if eta_val is not None and hasattr(eta_val, "total_seconds"):
                eta_sec = int(eta_val.total_seconds())
            elif isinstance(eta_val, (int, float)):
                eta_sec = int(eta_val)

            out.append(
                TorrentInfo(
                    id=t.id,
                    name=t.name,
                    percent=float(getattr(t, "progress", 0.0)),
                    status=str(t.status),
                    down_rate=int(getattr(t, "rate_download", 0)),
                    up_rate=int(getattr(t, "rate_upload", 0)),
                    size=int(getattr(t, "total_size", 0)),
                    eta=eta_sec,
                    peers_connected=int(getattr(t, "peers_connected", 0)),
                    peers_sending=int(getattr(t, "peers_sending_to_us", 0)),
                    error_string=str(getattr(t, "error_string", "") or ""),
                    info_hash=str(getattr(t, "hashString", "") or ""),
                )
            )
        return out

    async def pause(self, torrent_id: int) -> None:
        await self._run(lambda c: c.stop_torrent(torrent_id))

    async def resume(self, torrent_id: int) -> None:
        await self._run(lambda c: c.start_torrent(torrent_id))

    async def remove(self, torrent_id: int, delete_data: bool = False) -> None:
        await self._run(lambda c: c.remove_torrent(torrent_id, delete_data=delete_data))

    async def test(self) -> tuple[bool, str]:
        """Connection check for the status panel: never raises, never echoes credentials."""
        try:
            version, count = await self._run(
                lambda c: (c.get_session().version, c.session_stats().torrent_count)
            )
        except TransmissionAuthError:
            return False, "Identifiants refusés (401)."
        except TransmissionTimeoutError:  # subclass of TransmissionConnectError: keep it first
            return False, "Pas de réponse (timeout)."
        except TransmissionConnectError:
            return False, f"Injoignable ({self._config.host}:{self._config.port})."
        except Exception as exc:
            return False, redact(str(exc))
        label = str(version).split()[0] if version else "?"
        return True, f"v{label} · {count} torrent{'s' if count != 1 else ''}"
