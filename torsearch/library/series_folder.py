"""The folder a followed series is filed in: the one where it already lives.

Jellyfin makes one series of each folder of a TV library. Building the folder name from
the TMDB title ("Rick et Morty") next to an existing folder ("Rick.and.Morty") makes a
second series. So the existing folder is reused, in this order:

1. the folder Jellyfin knows for this TMDB id (exact; it wins over a remembered folder,
   so a folder renamed or merged by hand is followed);
2. the folder remembered on the series (``WantedSeries.folder``);
3. the folder a torrent of the show already sits in (not remembered: Jellyfin confirms
   it once it has scanned it);
4. otherwise the old ``Title/`` folder for a show with history (filed by the old code),
   or ``Title (Year) [tmdbid-N]``, which Jellyfin identifies for sure, for a new one.

A folder is remembered only after a successful send, and a made-up one only when
Jellyfin really answered: an outage must never pin a duplicate folder for good.

A release of a show nobody follows (manual send, free search) has no TMDB id: its folder
is found by name in Jellyfin (title, original title, year), then in Transmission
(``find_release_folder``); two shows of the same name are never guessed between.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from torsearch.library.episodes import parse_episodes, sanitize_folder_name
from torsearch.models import WantedSeries

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"^(19|20)\d\d$")


@dataclass(frozen=True)
class FolderChoice:
    path: str
    remember: bool  # store it on the series once a release was sent there


def _parts(path: str) -> list[str] | None:
    """Path components, or None when one is "." or ".." (never leave the TV folder)."""
    parts = [p for p in PurePosixPath(path.replace("\\", "/")).parts if p not in ("/", "")]
    return None if any(p in (".", "..") for p in parts) else parts


def _base(base_dir: str) -> str:
    return base_dir.rstrip("/\\") or "/"


def map_library_path(library_path: str, base_dir: str) -> str | None:
    """Jellyfin's series folder seen from Transmission, when it lies directly in ``base_dir``.

    Containers mount the same disk under different roots (``/media/disk2`` for Jellyfin,
    ``/downloads/disk2`` for Transmission): the parents are compared from the end, without
    their mount root, like the "Dossiers" check of the status panel. Identical parents
    (same mount in both containers, ``/tv``) match too.
    """
    parts, base = _parts(library_path), _parts(base_dir)
    if not parts or len(parts) < 2 or not base:
        return None
    parent = parts[:-1]
    if parent != base:
        k = min(len(parent), len(base)) - 1
        if k < 1 or parent[-k:] != base[-k:]:
            return None
    return f"{_base(base_dir)}/{parts[-1]}"


def folder_in_base(download_dir: str, base_dir: str) -> str | None:
    """The first folder below ``base_dir`` that holds ``download_dir`` (None outside it)."""
    parts, base = _parts(download_dir), _parts(base_dir)
    if parts is None or base is None or len(parts) <= len(base) or parts[: len(base)] != base:
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


def _legacy_folder(base_dir: str, series: WantedSeries) -> str:
    """Where the code before v0.12.2 filed the show: ``Title/``."""
    return f"{_base(base_dir)}/{sanitize_folder_name(series.title)}"


async def _jellyfin_paths(series: WantedSeries, jellyfin) -> list[tuple[str, int]] | None:
    """Jellyfin's folders for the show; None when Jellyfin is off or did not answer."""
    if jellyfin is None or not getattr(jellyfin, "enabled", False) or not hasattr(jellyfin, "series_paths"):
        return None
    try:
        return await jellyfin.series_paths(series.tmdb_id)
    except Exception as exc:
        logger.warning("Jellyfin series_paths() failed: %s", exc)
        return None


def _from_jellyfin(paths: list[tuple[str, int]], base_dir: str) -> str | None:
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
        # Only episodes of this show, in a folder named after it too (not "The Office (UK)/"
        # for The Office US, whose release names carry no year).
        if (folder and parse_episodes(t.name) and _series_matches(parse_release(t.name), series)
                and _series_matches(parse_release(folder.rsplit("/", 1)[1]), series)):
            folders[folder] += 1
    return folders.most_common(1)[0][0] if folders else None


async def find_series_folder(series: WantedSeries, base_dir: str, jellyfin=None, transmission=None) -> str | None:
    """Where the show already lives: Jellyfin first (exact TMDB id), then Transmission."""
    paths = await _jellyfin_paths(series, jellyfin)
    return (_from_jellyfin(paths, base_dir) if paths else None) or \
        await _from_transmission(series, base_dir, transmission)


def _remembered(series: WantedSeries, base_dir: str) -> str | None:
    folder = (series.folder or "").rstrip("/")
    return folder if folder and folder_in_base(folder + "/x", base_dir) == folder else None


async def choose_series_folder(series: WantedSeries, base_dir: str | None, jellyfin=None,
                               transmission=None) -> FolderChoice | None:
    """The folder ``series`` goes to (see the module docstring); None without a TV folder."""
    if not base_dir:
        return None
    paths = await _jellyfin_paths(series, jellyfin)
    if paths:
        folder = _from_jellyfin(paths, base_dir)
        if folder:
            return FolderChoice(folder, remember=True)
    remembered = _remembered(series, base_dir)
    if remembered:
        return FolderChoice(remembered, remember=False)
    folder = await _from_transmission(series, base_dir, transmission)
    if folder:
        return FolderChoice(folder, remember=False)
    jellyfin_answered = paths is not None or jellyfin is None or not getattr(jellyfin, "enabled", False)
    if series.grabbed:
        return FolderChoice(_legacy_folder(base_dir, series), remember=jellyfin_answered)
    return FolderChoice(new_series_folder(base_dir, series), remember=jellyfin_answered)


def remember_folder(series_library, series: WantedSeries, choice: FolderChoice | None) -> None:
    """Store the folder on the series after a successful send (when worth remembering)."""
    if choice is None or not choice.remember or series_library is None or not hasattr(series_library, "set_folder"):
        return
    if (series.folder or "").rstrip("/") != choice.path:
        series_library.set_folder(series.tmdb_id, choice.path)
        logger.info("Dossier de la serie %s : %s", series.title, choice.path)


async def _jellyfin_shows(jellyfin) -> list | None:
    if jellyfin is None or not getattr(jellyfin, "enabled", False) or not hasattr(jellyfin, "series_list"):
        return None
    try:
        return await jellyfin.series_list()
    except Exception as exc:
        logger.warning("Jellyfin series_list() failed: %s", exc)
        return None


def _match_jellyfin(rel, shows: list, base_dir: str) -> tuple[str | None, bool]:
    """The folder of the only Jellyfin show the release belongs to (fullest copy), and
    whether several shows matched (then nobody guesses, Transmission included)."""
    from torsearch.library.linking import _series_matches  # linking imports episodes; avoid a cycle

    groups: dict[str, list] = {}
    for show in shows:
        folder = map_library_path(show.path, base_dir) if show.path else None
        if not folder:
            continue
        candidate = WantedSeries(tmdb_id=0, title=show.name or folder.rsplit("/", 1)[1],
                                 original_title=show.original_title,
                                 year=str(show.year) if show.year else None, added_at=datetime.now(UTC))
        if _series_matches(rel, candidate):
            groups.setdefault(show.tmdb_id or show.path, []).append((show, folder))
    if len(groups) > 1 and rel.year:
        # The release year settles two shows of the same name (Shogun 1980 / 2024).
        groups = {k: v for k, v in groups.items() if any(s.year == rel.year for s, _ in v)}
    if len(groups) > 1:
        logger.info("Release %s matches several Jellyfin shows: default folder", rel.clean_title)
        return None, True
    if not groups:
        return None, False
    copies = next(iter(groups.values()))
    return max(copies, key=lambda c: c[0].episodes)[1], False


async def find_release_folder(rel, base_dir: str | None, jellyfin=None, transmission=None) -> str | None:
    """The folder an episode release of a show nobody follows already lives in (None: unknown)."""
    if not base_dir or not rel.episodes or not rel.clean_title:
        return None
    shows = await _jellyfin_shows(jellyfin)
    if shows:
        folder, ambiguous = _match_jellyfin(rel, shows, base_dir)
        if folder or ambiguous:
            return folder
    pseudo = WantedSeries(tmdb_id=0, title=rel.clean_title, year=str(rel.year) if rel.year else None,
                          added_at=datetime.now(UTC))
    return await _from_transmission(pseudo, base_dir, transmission)
