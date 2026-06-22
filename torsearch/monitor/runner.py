from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from torsearch.library.episodes import parse_episodes
from torsearch.models import Category, SearchResult
from torsearch.monitor.history import MonitorRecord
from torsearch.notifications.notifier import Notifier
from torsearch.search.filters import ResultFilters, apply

logger = logging.getLogger(__name__)


def grab_key(result: SearchResult) -> str:
    return result.infohash or result.download_url


def select_new(results, filters, seen):
    for result in apply(results, filters):
        if grab_key(result) not in seen:
            return result
    return None


async def run_cycle(config, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled:
        return []
    created: list[MonitorRecord] = []
    for saved in config.saved_searches:
        if not saved.enabled:
            continue
        try:
            results = await search_service.search(saved.query, saved.category)
        except Exception as exc:
            logger.warning("Monitor search '%s' failed: %s", saved.name, exc)
            continue
        filters = ResultFilters(
            min_seeders=saved.min_seeders, min_size=saved.min_size, max_size=saved.max_size,
            qualities=saved.qualities, exclude=saved.exclude, sort="seeders", direction="desc",
        )
        pick = select_new(results, filters, history.seen_keys(saved.name))
        if pick is None:
            continue
        if saved.mode == "auto":
            try:
                transmission.add(pick.download_url)
            except Exception as exc:
                logger.warning("Monitor grab for '%s' failed: %s", saved.name, exc)
                continue
            kind = "grabbed"
        else:
            kind = "found"
        record = MonitorRecord(
            search=saved.name, title=pick.title, source=pick.source,
            infohash=pick.infohash, download_url=pick.download_url,
            kind=kind, at=datetime.now(timezone.utc),
        )
        history.add(record)
        created.append(record)
        if notifier is not None:
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Notification for '%s' failed: %s", saved.name, exc)
    return created


async def run_movie_cycle(config, library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    for movie in library.wanted():
        query = f"{movie.title} {movie.year or ''}".strip()
        try:
            results = await search_service.search(query, Category.MOVIES)
        except Exception as exc:
            logger.warning("Movie search '%s' failed: %s", movie.title, exc)
            continue
        filters = ResultFilters(
            min_seeders=profile.min_seeders, qualities=profile.qualities,
            sort="seeders", direction="desc",
        )
        pick = select_new(results, filters, set())
        if pick is None:
            continue
        try:
            transmission.add(pick.download_url, download_dir=config.paths.for_category(Category.MOVIES))
        except Exception as exc:
            logger.warning("Movie grab '%s' failed: %s", movie.title, exc)
            continue
        now = datetime.now(timezone.utc)
        library.mark_grabbed(movie.tmdb_id, pick.title, now)
        record = MonitorRecord(
            search=f"{movie.title} ({movie.year})", title=pick.title, source=pick.source,
            infohash=pick.infohash, download_url=pick.download_url, kind="grabbed", at=now,
        )
        history.add(record)
        created.append(record)
        if notifier is not None:
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Movie notif '%s' failed: %s", movie.title, exc)
    return created


async def run_series_cycle(config, series_library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or series_library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    for series in series_library.list():
        try:
            results = await search_service.search(series.title, Category.TV)
        except Exception as exc:
            logger.warning("Series search '%s' failed: %s", series.title, exc)
            continue
        kept = apply(results, ResultFilters(
            min_seeders=profile.min_seeders, qualities=profile.qualities,
            sort="seeders", direction="desc",
        ))
        have = set(series.grabbed)
        newly: list[str] = []
        for r in kept:
            keys = parse_episodes(r.title)
            if not keys - have:
                continue
            try:
                transmission.add(r.download_url, download_dir=config.paths.for_category(Category.TV))
            except Exception as exc:
                logger.warning("Series grab '%s' failed: %s", series.title, exc)
                continue
            have |= keys
            newly.extend(keys)
            now = datetime.now(timezone.utc)
            record = MonitorRecord(
                search=series.title, title=r.title, source=r.source,
                infohash=r.infohash, download_url=r.download_url, kind="grabbed", at=now,
            )
            history.add(record)
            created.append(record)
            if notifier is not None:
                try:
                    await notifier.notify(config.notifications, record)
                except Exception as exc:
                    logger.warning("Series notif '%s' failed: %s", series.title, exc)
        if newly:
            series_library.mark_grabbed(series.tmdb_id, sorted(set(newly)))
    return created


class MonitorRunner:
    def __init__(self, ctx, history, notifier=None, library=None, series_library=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
        self._library = library
        self._series_library = series_library
        self._task = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await run_cycle(
                    self._ctx.config, self._ctx.search_service, self._ctx.transmission,
                    self._history, self._notifier,
                )
                await run_movie_cycle(
                    self._ctx.config, self._library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                )
                await run_series_cycle(
                    self._ctx.config, self._series_library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                )
            except Exception:
                logger.exception("Monitor cycle failed")
            interval = max(self._ctx.config.monitor.interval_minutes, 1) * 60
            await asyncio.sleep(interval)
