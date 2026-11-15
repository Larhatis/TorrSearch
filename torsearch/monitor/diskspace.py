"""Free space on the download disks, as Transmission sees them.

TorrSearch does not mount the disks: only Transmission can measure them (RPC ``free-space``).
An unknown free space never blocks a download: a broken check must not stop the surveillance.
"""

from __future__ import annotations

import logging

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


async def _free(transmission, path: str | None) -> int | None:
    measure = getattr(transmission, "free_space", None)
    if measure is None:
        return None
    try:
        return await measure(path)
    except Exception as exc:  # the facade never raises, test doubles might
        logger.debug("Free space of %s unknown: %s", path, exc)
        return None


async def has_room(transmission, download_dir: str | None, size: int, min_free: int) -> bool:
    """Whether sending ``size`` bytes to ``download_dir`` leaves at least ``min_free`` bytes.

    False only when the free space is known and too small; ``min_free`` 0 disables the check.
    """
    if min_free <= 0:
        return True
    free = await _free(transmission, download_dir)
    if free is None:
        logger.debug("Free space of %s unknown: sending anyway", download_dir or "default folder")
        return True
    return free - max(size, 0) >= min_free


def _folders(config) -> list[tuple[str, str | None]]:
    """(label, path) of every distinct download folder; None is Transmission's default."""
    by_path: dict[str, list[str]] = {}
    for category, path in config.paths.by_category.items():
        if path:
            by_path.setdefault(path, []).append(_LABELS.get(category, category))
    folders: list[tuple[str, str | None]] = [(", ".join(labels), path) for path, labels in by_path.items()]
    if not config.paths.by_category.get("movies") or not config.paths.by_category.get("tv"):
        folders.append((DEFAULT_LABEL, None))
    return folders


async def folder_usage(transmission, config) -> list[tuple[str, str | None, int | None]]:
    """(label, path, free bytes or None) of every download folder, for the status panel."""
    return [(label, path, await _free(transmission, path)) for label, path in _folders(config)]


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
