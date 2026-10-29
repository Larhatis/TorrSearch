from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)

_TMDB_CONCURRENCY = 4


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
    limit = asyncio.Semaphore(_TMDB_CONCURRENCY)  # stay under TMDB's rate limit

    async def bounded(job):
        async with limit:
            return await job

    jobs = [bounded(_series_entries(tmdb, s, today, start, end)) for s in series_list]
    jobs += [bounded(_movie_entry(tmdb, m, today, start, end)) for m in movies]
    by_day: dict[date, list[CalendarEntry]] = {}
    for entries in await asyncio.gather(*jobs):
        for entry in entries:
            by_day.setdefault(entry.day, []).append(entry)
    return [
        (day, sorted(by_day[day], key=lambda e: (e.kind, e.title, e.detail)))
        for day in sorted(by_day)
    ]


def _ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """RFC 5545: lines of at most 75 octets, continuations start with a space."""
    out: list[str] = []
    current = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode()) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + part for part in out[1:]]


def build_ics(days: list[tuple[date, list[CalendarEntry]]], now: datetime | None = None) -> str:
    """The "A venir" calendar as an iCalendar feed (all-day events), for phone calendars."""
    import hashlib

    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TorrSearch//A venir//FR",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:TorrSearch - A venir",
        # RFC 5545 requires at least one component, even when nothing is scheduled.
        "BEGIN:VTIMEZONE", "TZID:UTC", "BEGIN:STANDARD", "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0000", "TZOFFSETTO:+0000", "END:STANDARD", "END:VTIMEZONE",
    ]
    status_label = {"acquired": "Acquis", "missing": "En recherche", "upcoming": "A venir"}
    for day, entries in days:
        for e in entries:
            uid = hashlib.sha1(f"{e.link}|{e.detail}".encode()).hexdigest()[:20]
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}@torrsearch",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_ics_escape(e.title)} · {_ics_escape(e.detail)}",
                f"DESCRIPTION:{_ics_escape(status_label.get(e.status, e.status))}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "".join(f"{part}\r\n" for line in lines for part in _fold(line))
