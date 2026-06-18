from __future__ import annotations

from abc import ABC, abstractmethod

from torsearch.models import Category, SearchResult


class Indexer(ABC):
    name: str
    enabled: bool

    @abstractmethod
    async def search(self, query: str, category: Category) -> list[SearchResult]:
        ...
