"""Free space on the download disks, as Transmission sees them.

TorrSearch does not mount the disks: only Transmission can measure them (RPC ``free-space``).
An unknown free space never blocks a download: a broken check must not stop the surveillance.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

_LABELS = {"movies": "Films", "tv": "Series", "anime": "Anime", "other": "Autres"}
DEFAULT_LABEL = "Par defaut"


def format_bytes(n: int) -> str:
    """``638 Go``, ``4,5 Go``, ``1,9 To`` (decimal units, like disk vendors and Transmission)."""
    if n >= 1e12:
        return f"{n / 1e12:.1f} To".replace(".", ",")
    gb = n / 1e9
    text = f"{gb:.0f}" if gb >= 10 else f"{gb:.1f}".replace(".", ",")
    return f"{text} Go"


async def free_bytes(transmission, path: str | None) -> int | None:
    """Free bytes on the disk of ``path`` (None: unknown, or a transport without the RPC)."""
    measure = getattr(transmission, "free_space", None)
    if measure is None:
        return None
    try:
        return await measure(path)
    except Exception as exc:  # the facade never raises, test doubles might
        logger.debug("Free space of %s unknown: %s", path, exc)
        return None


def _parts(path: str) -> tuple[str, ...]:
    return PurePosixPath(path).parts


class DiskBudget:
    """Free space for one monitor cycle, minus what is already promised to Transmission.

    Transmission does not reserve space when a torrent is added (sparse files): measuring
    again before each send would let five 40 GB packs through on 120 GB. The budget subtracts
    what unfinished torrents still have to write and what this cycle already sent, per
    download folder of the settings (each one stands for a disk).
    """

    def __init__(self, transmission, config):
        self._transmission = transmission
        self._config = config
        self._roots = sorted({p for p in config.paths.by_category.values() if p}, key=len, reverse=True)
        self._pending: dict[str, int] | None = None
        self._reserved: dict[str, int] = {}
        self._free: dict[str | None, int | None] = {}
        self.refused = 0  # sends refused this cycle

    def _key(self, download_dir: str | None) -> str:
        """The settings folder holding ``download_dir`` ("" for Transmission's default)."""
        if download_dir:
            parts = _parts(download_dir)
            for root in self._roots:
                root_parts = _parts(root)
                if parts[: len(root_parts)] == root_parts:
                    return root
        return ""

    async def _pending_bytes(self, key: str) -> int:
        if self._pending is None:
            self._pending = {}
            try:
                torrents = await self._transmission.list_torrents()
            except Exception as exc:
                logger.debug("Listing torrents for the disk budget failed: %s", exc)
                torrents = []
            for t in torrents:
                if t.percent < 100.0 and t.size > 0:
                    left = int(t.size * (100.0 - max(t.percent, 0.0)) / 100.0)
                    k = self._key(t.download_dir or None)
                    self._pending[k] = self._pending.get(k, 0) + left
        return self._pending.get(key, 0)

    async def has_room(self, download_dir: str | None, size: int) -> bool:
        min_free = self._config.library.min_free_bytes
        if min_free <= 0:
            return True
        if download_dir not in self._free:
            self._free[download_dir] = await free_bytes(self._transmission, download_dir)
        free = self._free[download_dir]
        if free is None:
            logger.debug("Free space of %s unknown: sending anyway", download_dir or "default folder")
            return True
        key = self._key(download_dir)
        promised = self._reserved.get(key, 0) + await self._pending_bytes(key)
        if free - promised - max(size, 0) >= min_free:
            return True
        self.refused += 1
        return False

    def reserve(self, download_dir: str | None, size: int) -> None:
        """Count a send of this cycle against its disk."""
        key = self._key(download_dir)
        self._reserved[key] = self._reserved.get(key, 0) + max(size, 0)


def _folders(config) -> list[tuple[str, str | None]]:
    """(label, path) of every distinct download folder; None is Transmission's default."""
    by_path: dict[str, list[str]] = {}
    for category, path in config.paths.by_category.items():
        if path:
            by_path.setdefault(path, []).append(_LABELS.get(category, category))
    folders: list[tuple[str, str | None]] = [(", ".join(labels), path) for path, labels in by_path.items()]
    paths = config.paths.by_category
    uses_default = not paths.get("movies") or not paths.get("tv") or any(
        not paths.get(s.category.value) for s in config.saved_searches if s.enabled and s.mode == "auto"
    )
    if uses_default:
        folders.append((DEFAULT_LABEL, None))
    return folders


async def folder_usage(transmission, config) -> list[tuple[str, str | None, int | None]]:
    """(label, path, free bytes or None) of every download folder, for the status panel."""
    folders = _folders(config)
    frees = await asyncio.gather(*(free_bytes(transmission, path) for _label, path in folders))
    return [(label, path, free) for (label, path), free in zip(folders, frees, strict=True)]


async def low_folders(transmission, config) -> list[tuple[str, str | None, int]]:
    """Download folders whose disk is under the profile's free-space threshold."""
    min_free = config.library.min_free_bytes
    if min_free <= 0:
        return []
    return [
        (label, path, free)
        for label, path, free in await folder_usage(transmission, config)
        if free is not None and free < min_free
    ]
