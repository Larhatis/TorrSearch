import asyncio

from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService


def _result(title, seeders, source="t", infohash=None, size=1000):
    return SearchResult(
        title=title,
        size=size,
        seeders=seeders,
        leechers=0,
        source=source,
        category=Category.MOVIES,
        download_url=f"magnet:?xt=urn:btih:{title}",
        infohash=infohash,
    )


class FakeIndexer:
    def __init__(self, name, results=None, error=None, delay=0.0, enabled=True):
        self.name = name
        self.enabled = enabled
        self._results = results or []
        self._error = error
        self._delay = delay

    async def search(self, query, category):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return list(self._results)


async def test_merges_and_sorts_by_seeders_desc():
    a = FakeIndexer("a", [_result("low", 5, "a")])
    b = FakeIndexer("b", [_result("high", 50, "b")])
    service = SearchService([a, b])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["high", "low"]


async def test_failing_indexer_is_ignored():
    good = FakeIndexer("good", [_result("ok", 10, "good")])
    bad = FakeIndexer("bad", error=RuntimeError("boom"))
    service = SearchService([good, bad])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["ok"]


async def test_timed_out_indexer_is_ignored():
    slow = FakeIndexer("slow", [_result("slow", 99, "slow")], delay=0.2)
    fast = FakeIndexer("fast", [_result("fast", 1, "fast")])
    service = SearchService([slow, fast], timeout=0.05)
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["fast"]


async def test_dedupe_by_infohash_keeps_higher_seeders():
    a = FakeIndexer("a", [_result("dup", 10, "a", infohash="HASH")])
    b = FakeIndexer("b", [_result("dup", 80, "b", infohash="HASH")])
    service = SearchService([a, b])
    out = await service.search("q", Category.ALL)
    assert len(out) == 1
    assert out[0].seeders == 80


async def test_disabled_indexer_not_queried():
    enabled = FakeIndexer("on", [_result("on", 10, "on")])
    disabled = FakeIndexer("off", [_result("off", 99, "off")], enabled=False)
    service = SearchService([enabled, disabled])
    out = await service.search("q", Category.ALL)
    assert [r.title for r in out] == ["on"]


def test_indexers_property_exposes_list():
    a = FakeIndexer("a")
    service = SearchService([a])
    assert service.indexers == [a]
