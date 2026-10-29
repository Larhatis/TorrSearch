from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from torsearch.indexers.base import Indexer, RateLimited
from torsearch.indexers.throttle import TrackerThrottle
from torsearch.models import Category, SearchResult
from torsearch.search.relevance import compute_relevance

logger = logging.getLogger(__name__)

_OLDEST = datetime.min.replace(tzinfo=UTC)


class SearchService:
    def __init__(
        self,
        indexers: list[Indexer],
        timeout: float = 10.0,
        throttles: dict[str, TrackerThrottle] | None = None,
        min_interval: float = 2.0,
    ):
        self._indexers = indexers
        self._timeout = timeout
        # Shared with the AppContext so spacing and 429 pauses survive settings changes.
        self._throttles = throttles
        if throttles is not None:
            for ix in indexers:
                throttle = throttles.setdefault(ix.name, TrackerThrottle(min_interval))
                throttle.min_interval = min_interval

    @property
    def indexers(self) -> list[Indexer]:
        return self._indexers

    def available(self) -> bool:
        """Whether at least one active tracker is not paused (HTTP 429)."""
        return any(
            ix.enabled and not (self._throttles is not None and ix.name in self._throttles
                                and self._throttles[ix.name].is_blocked())
            for ix in self._indexers
        )

    async def search(self, query: str, category: Category = Category.ALL,
                     only: frozenset[str] | None = None) -> list[SearchResult]:
        deduped = await self._gather(query, category, only)
        if query.strip():
            deduped.sort(key=lambda r: (compute_relevance(r, query), r.seeders), reverse=True)
        else:
            deduped.sort(key=lambda r: r.seeders, reverse=True)
        return deduped

    async def recent(self, category: Category = Category.ALL) -> list[SearchResult]:
        """Latest releases of every tracker (Torznab search without text = RSS feed)."""
        deduped = await self._gather("", category)
        deduped.sort(key=lambda r: r.publish_date or _OLDEST, reverse=True)
        return deduped

    async def _gather(self, query: str, category: Category,
                      only: frozenset[str] | None = None) -> list[SearchResult]:
        active = [ix for ix in self._indexers if ix.enabled and (only is None or ix.name in only)]
        results_lists = await asyncio.gather(*(self._search_one(ix, query, category) for ix in active))
        merged = [r for lst in results_lists for r in lst]
        return self._dedupe(merged)

    async def _search_one(
        self, indexer: Indexer, query: str, category: Category
    ) -> list[SearchResult]:
        throttle = self._throttles.get(indexer.name) if self._throttles is not None else None
        if throttle is None:
            return await self._query(indexer, query, category)
        if throttle.is_blocked():
            logger.info("Tracker %s en pause (limite de requetes), ignore.", indexer.name)
            return []
        # The wait in the throttle queue is not counted in the request timeout.
        async with throttle:
            if throttle.is_blocked():  # paused by a 429 while we were queued
                return []
            try:
                return await self._query(indexer, query, category, reraise_limit=True)
            except RateLimited as exc:
                throttle.block(exc.retry_after)
                logger.warning(
                    "Tracker %s : limite de requetes atteinte (HTTP 429), pause de %d min.",
                    indexer.name, round(exc.retry_after / 60),
                )
                return []

    async def _query(
        self, indexer: Indexer, query: str, category: Category, reraise_limit: bool = False
    ) -> list[SearchResult]:
        try:
            return await asyncio.wait_for(indexer.search(query, category), timeout=self._timeout)
        except RateLimited:
            if reraise_limit:
                raise
            logger.warning("Search on %s failed: rate limited", indexer.name)
            return []
        except Exception as exc:  # resilience: one tracker must not break the search
            logger.warning("Search on %s failed: %s", indexer.name, exc)
            return []

    @staticmethod
    def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
        best: dict[str, SearchResult] = {}
        for r in results:
            key = r.infohash.lower() if r.infohash else f"{r.title.lower()}|{r.size}"
            existing = best.get(key)
            if existing is None or r.seeders > existing.seeders:
                best[key] = r
        return list(best.values())
