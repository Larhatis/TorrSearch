from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from torsearch.library.episodes import build_movie_download_dir, build_tv_download_dir
from torsearch.models import Category, WantedMovie, WantedSeries
from torsearch.monitor.history import MonitorHistory, MonitorRecord
from torsearch.parser.release import ParsedRelease, parse_release
from torsearch.search.matcher import match_media_title


@dataclass
class ManualGrab:
    """Where a manually chosen release goes, and the watched item it satisfies (if any)."""

    title: str
    parsed: ParsedRelease
    download_dir: str | None
    movie: WantedMovie | None = None
    series: WantedSeries | None = None

    @property
    def watched_title(self) -> str | None:
        if self.movie is not None:
            return self.movie.title
        return self.series.title if self.series is not None else None


def plan_manual_grab(title: str, category: Category, paths, library=None, series_library=None) -> ManualGrab:
    """Route a manual download like the monitor would: series/season folders for episodes,
    ``Title (Year) [tmdbid-N]`` for movies, linked to the watched item when one matches."""
    rel = parse_release(title)
    if (rel.episodes or category == Category.TV) and rel.clean_title:
        series = None
        if rel.episodes:  # nothing to mark for a release without SxxEyy (integrale...)
            series = next(
                (s for s in (series_library.list() if series_library is not None else [])
                 if _series_matches(rel, s)),
                None,
            )
        name = series.title if series is not None else rel.clean_title
        download_dir = build_tv_download_dir(
            base_dir=paths.for_category(Category.TV), series_title=name,
            episodes=rel.episodes, release_title=title,
        )
        return ManualGrab(title, rel, download_dir, series=series)

    movie = None
    if title and not rel.is_banned_source and rel.year:
        # Both years required: without them a remake (The Thing 1982 / 2011) would match.
        movie = next(
            (m for m in (library.list() if library is not None else [])
             if m.year and match_media_title(rel, target_title=m.title, target_original_title=m.original_title,
                                             target_year=m.year)),
            None,
        )
    if movie is not None:
        base = paths.for_category(Category.MOVIES)
        return ManualGrab(title, rel, build_movie_download_dir(base, movie.title, movie.year, movie.tmdb_id),
                          movie=movie)
    if category == Category.MOVIES and rel.clean_title and rel.year:
        base = paths.for_category(Category.MOVIES)
        return ManualGrab(title, rel, build_movie_download_dir(base, rel.clean_title, rel.year, None))
    return ManualGrab(title, rel, paths.for_category(category))


def _series_matches(rel: ParsedRelease, series: WantedSeries) -> bool:
    if not match_media_title(rel, target_title=series.title, target_original_title=series.original_title,
                             is_series=True):
        return False
    # A release older than the show is another show (Shogun 1980 vs Shogun 2024).
    if rel.year and series.year and series.year[:4].isdigit():
        return rel.year >= int(series.year[:4]) - 1
    return True


def record_manual_grab(grab: ManualGrab, download_url: str, library=None, series_library=None,
                       history: MonitorHistory | None = None) -> None:
    """Mark the watched item as acquired so the monitor does not download it again."""
    now = datetime.now(UTC)
    if grab.movie is not None and library is not None:
        library.mark_grabbed(grab.movie.tmdb_id, grab.title, now)
        search = f"{grab.movie.title} ({grab.movie.year})"
    elif grab.series is not None and series_library is not None:
        series_library.mark_grabbed(grab.series.tmdb_id, sorted(grab.parsed.episodes))
        search = grab.series.title
    else:
        return
    if history is not None:
        history.add(MonitorRecord(search=search, title=grab.title, source="manuel",
                                  download_url=download_url, kind="grabbed", at=now))
