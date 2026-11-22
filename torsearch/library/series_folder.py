"""The folder a followed series is filed in: the one where it already lives.

Jellyfin makes one series of each folder of a TV library. Building the folder name from
the TMDB title ("Rick et Morty") next to an existing folder ("Rick.and.Morty") makes a
second series. So the existing folder is reused: the one Jellyfin knows for this TMDB id
(exact), else the one a torrent of the show already sits in. A show seen nowhere gets
``Title (Year) [tmdbid-N]``, which Jellyfin identifies for sure. The choice is stored on
the series so every later grab goes to the same place.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import PurePosixPath

from torsearch.library.episodes import sanitize_folder_name
from torsearch.models import WantedSeries

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"^(19|20)\d\d$")


def _parts(path: str) -> list[str]:
    return [p for p in PurePosixPath(path.replace("\\", "/")).parts if p not in ("/", "")]


def _base(base_dir: str) -> str:
    return base_dir.rstrip("/\\") or "/"


def map_library_path(library_path: str, base_dir: str) -> str | None:
    """Jellyfin's series folder seen from Transmission, when it lies directly in ``base_dir``.

    Containers mount the same disk under different roots (``/media/disk2`` for Jellyfin,
    ``/downloads/disk2`` for Transmission): the parents are compared from the end, without
    their mount root, like the "Dossiers" check of the status panel.
    """
    parts, base = _parts(library_path), _parts(base_dir)
    if len(parts) < 2 or not base:
        return None
    parent = parts[:-1]
    k = min(len(parent), len(base)) - 1
    if k < 1 or parent[-k:] != base[-k:]:
        return None
    return f"{_base(base_dir)}/{parts[-1]}"


def folder_in_base(download_dir: str, base_dir: str) -> str | None:
    """The first folder below ``base_dir`` that holds ``download_dir`` (None outside it)."""
    parts, base = _parts(download_dir), _parts(base_dir)
    if len(parts) <= len(base) or parts[: len(base)] != base:
        return None
    return f"{_base(base_dir)}/{parts[len(base)]}"


def new_series_folder(base_dir: str, series: WantedSeries) -> str:
    """``Title (Year) [tmdbid-N]`` in ``base_dir`` (the year only when it is a plain year)."""
    name = sanitize_folder_name(re.sub(r"\s*:\s*", " - ", series.title.strip()))
    year = (series.year or "").strip()[:4]
    if _YEAR_RE.match(year):
        name = f"{name} ({year})"
    name = f"{name} [tmdbid-{int(series.tmdb_id)}]"
    return f"{_base(base_dir)}/{sanitize_folder_name(name)}"


async def _from_jellyfin(series: WantedSeries, base_dir: str, jellyfin) -> str | None:
    if jellyfin is None or not getattr(jellyfin, "enabled", False) or not hasattr(jellyfin, "series_paths"):
        return None
    try:
        paths = await jellyfin.series_paths(series.tmdb_id)
    except Exception as exc:
        logger.warning("Jellyfin series_paths() failed: %s", exc)
        return None
    # Two folders for one show (the bug this module fixes): keep the fuller one.
    for path, _count in sorted(paths, key=lambda p: -p[1]):
        folder = map_library_path(path, base_dir)
        if folder:
            return folder
    return None


async def _from_transmission(series: WantedSeries, base_dir: str, transmission) -> str | None:
    if transmission is None or not hasattr(transmission, "list_torrents"):
        return None
    try:
        torrents = await transmission.list_torrents()
    except Exception as exc:
        logger.warning("Transmission list for series folder failed: %s", exc)
        return None
    from torsearch.library.linking import _series_matches  # linking imports episodes; avoid a cycle
    from torsearch.parser.release import parse_release

    folders: Counter[str] = Counter()
    for t in torrents:
        folder = folder_in_base(getattr(t, "download_dir", "") or "", base_dir)
        if folder and _series_matches(parse_release(t.name), series):
            folders[folder] += 1
    return folders.most_common(1)[0][0] if folders else None


async def find_series_folder(series: WantedSeries, base_dir: str, jellyfin=None, transmission=None) -> str | None:
    """Where the show already lives: Jellyfin first (exact TMDB id), then Transmission."""
    return await _from_jellyfin(series, base_dir, jellyfin) or await _from_transmission(series, base_dir, transmission)


async def series_folder(series: WantedSeries, base_dir: str | None, jellyfin=None, transmission=None,
                        series_library=None) -> str | None:
    """The folder ``series`` goes to, chosen once and remembered on the series.

    None without a TV folder in the settings (Transmission's default folder).
    """
    if not base_dir:
        return None
    if series.folder and folder_in_base(series.folder + "/x", base_dir) == series.folder.rstrip("/"):
        return series.folder.rstrip("/")
    folder = await find_series_folder(series, base_dir, jellyfin, transmission) or new_series_folder(base_dir, series)
    if series_library is not None and hasattr(series_library, "set_folder"):
        series_library.set_folder(series.tmdb_id, folder)
    logger.info("Dossier de la serie %s : %s", series.title, folder)
    return folder
