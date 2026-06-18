from __future__ import annotations

from torsearch.config import Config
from torsearch.indexers.base import Indexer
from torsearch.indexers.torznab import TorznabIndexer


def build_indexers(config: Config) -> list[Indexer]:
    indexers: list[Indexer] = []
    for ic in config.indexers:
        if not ic.enabled:
            continue
        if ic.type == "torznab":
            indexers.append(TorznabIndexer(ic, timeout=config.search.timeout_seconds))
    return indexers
