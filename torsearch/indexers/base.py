from __future__ import annotations

from abc import ABC, abstractmethod

from torsearch.models import Category, SearchResult

DEFAULT_RETRY_AFTER = 900.0


class RateLimited(Exception):
    """The tracker answered HTTP 429: callers must pause it for ``retry_after`` seconds."""

    def __init__(self, retry_after: float = DEFAULT_RETRY_AFTER):
        super().__init__(f"rate limited for {retry_after:.0f}s")
        self.retry_after = retry_after


class Indexer(ABC):
    name: str
    enabled: bool

    @abstractmethod
    async def search(self, query: str, category: Category) -> list[SearchResult]:
        ...
