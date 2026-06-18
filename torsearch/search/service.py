from __future__ import annotations

import asyncio
import logging

from torsearch.indexers.base import Indexer
from torsearch.models import Category, SearchResult

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, indexers: list[Indexer], timeout: float = 10.0):
        self._indexers = indexers
        self._timeout = timeout

    @property
    def indexers(self) -> list[Indexer]:
        return self._indexers

    async def search(self, query: str, category: Category = Category.ALL) -> list[SearchResult]:
        active = [ix for ix in self._indexers if ix.enabled]
        results_lists = await asyncio.gather(*(self._search_one(ix, query, category) for ix in active))
        merged = [r for lst in results_lists for r in lst]
        deduped = self._dedupe(merged)
        deduped.sort(key=lambda r: r.seeders, reverse=True)
        return deduped

    async def _search_one(
        self, indexer: Indexer, query: str, category: Category
    ) -> list[SearchResult]:
        try:
            return await asyncio.wait_for(indexer.search(query, category), timeout=self._timeout)
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
