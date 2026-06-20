from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from torsearch.models import SearchResult
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


class MonitorRunner:
    def __init__(self, ctx, history, notifier=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
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
            except Exception:
                logger.exception("Monitor cycle failed")
            interval = max(self._ctx.config.monitor.interval_minutes, 1) * 60
            await asyncio.sleep(interval)
