from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalendarEntry:
    day: date
    kind: str  # "episode" | "movie"
    title: str
    detail: str
    link: str
    poster_url: str | None
    status: str  # "acquired" | "missing" | "upcoming"


def _status(acquired: bool, day: date, today: date) -> str:
    if acquired:
        return "acquired"
    return "missing" if day <= today else "upcoming"


async def _series_entries(tmdb, series, today: date, start: date, end: date) -> list[CalendarEntry]:
    try:
        seasons = await tmdb.seasons(series.tmdb_id)
    except Exception as exc:
        logger.warning("Calendar: TMDB seasons for '%s' failed: %s", series.title, exc)
        return []
    grabbed = set(series.grabbed)
    entries: list[CalendarEntry] = []
    for season in seasons:
        for ep in season.episodes:
            if not ep.air_date:
                continue
            try:
                day = date.fromisoformat(ep.air_date)
            except ValueError:
                continue
            if not start <= day <= end:
                continue
            acquired = ep.code in grabbed or season.season_tag in grabbed
            entries.append(CalendarEntry(
                day=day, kind="episode", title=series.title,
                detail=f"{ep.code} · {ep.name}" if ep.name else ep.code,
                link=f"/series/{series.tmdb_id}", poster_url=series.poster_url,
                status=_status(acquired, day, today),
            ))
    return entries


async def _movie_entry(tmdb, movie, today: date, start: date, end: date) -> list[CalendarEntry]:
    try:
        release = await tmdb.release_date(movie.tmdb_id)
    except Exception as exc:
        logger.warning("Calendar: TMDB release date for '%s' failed: %s", movie.title, exc)
        return []
    if release is None:
        return []
    when, kind = release
    try:
        day = date.fromisoformat(when)
    except ValueError:
        return []
    if not start <= day <= end:
        return []
    label = "Sortie numerique" if kind == "numerique" else "Sortie cinema"
    return [CalendarEntry(
        day=day, kind="movie", title=movie.title, detail=label,
        link=f"/movies/{movie.tmdb_id}", poster_url=movie.poster_url,
        status=_status(movie.status == "grabbed", day, today),
    )]


async def build_calendar(
    tmdb, series_list, movies, today: date, past_days: int = 7, future_days: int = 60,
) -> list[tuple[date, list[CalendarEntry]]]:
    """Episodes of followed series and releases of watched movies, grouped by day."""
    if tmdb is None or not getattr(tmdb, "enabled", False):
        return []
    start, end = today - timedelta(days=past_days), today + timedelta(days=future_days)
    jobs = [_series_entries(tmdb, s, today, start, end) for s in series_list]
    jobs += [_movie_entry(tmdb, m, today, start, end) for m in movies]
    by_day: dict[date, list[CalendarEntry]] = {}
    for entries in await asyncio.gather(*jobs):
        for entry in entries:
            by_day.setdefault(entry.day, []).append(entry)
    return [
        (day, sorted(by_day[day], key=lambda e: (e.kind, e.title, e.detail)))
        for day in sorted(by_day)
    ]
