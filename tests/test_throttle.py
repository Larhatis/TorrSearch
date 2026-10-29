import asyncio

import httpx
import pytest
import respx

from torsearch.config import IndexerConfig
from torsearch.indexers.throttle import TrackerThrottle
from torsearch.indexers.torznab import RateLimited, TorznabIndexer
from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


async def test_throttle_spaces_consecutive_requests():
    clock = FakeClock()
    throttle = TrackerThrottle(min_interval=2.0, clock=clock, sleep=clock.sleep)
    async with throttle:
        pass
    clock.now += 0.5
    async with throttle:
        pass
    assert clock.slept == [pytest.approx(1.5)]


async def test_throttle_does_not_wait_after_interval_elapsed():
    clock = FakeClock()
    throttle = TrackerThrottle(min_interval=2.0, clock=clock, sleep=clock.sleep)
    async with throttle:
        pass
    clock.now += 5
    async with throttle:
        pass
    assert clock.slept == []


async def test_throttle_serializes_requests():
    throttle = TrackerThrottle(min_interval=0.0)
    active = 0
    peak = 0

    async def job():
        nonlocal active, peak
        async with throttle:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(job(), job(), job())
    assert peak == 1


def test_throttle_block_expires():
    clock = FakeClock()
    throttle = TrackerThrottle(min_interval=0.0, clock=clock)
    throttle.block(60)
    assert throttle.is_blocked()
    clock.now += 61
    assert not throttle.is_blocked()


@respx.mock
async def test_torznab_raises_rate_limited_with_retry_after():
    respx.get("https://t.example/api").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "120"})
    )
    ix = TorznabIndexer(IndexerConfig(name="t", url="https://t.example/api", api_key="k"))
    with pytest.raises(RateLimited) as info:
        await ix.search("dune", Category.ALL)
    assert info.value.retry_after == 120


@respx.mock
async def test_torznab_rate_limited_defaults_to_15_minutes():
    respx.get("https://t.example/api").mock(return_value=httpx.Response(429))
    ix = TorznabIndexer(IndexerConfig(name="t", url="https://t.example/api", api_key="k"))
    with pytest.raises(RateLimited) as info:
        await ix.search("dune", Category.ALL)
    assert info.value.retry_after == 900


def _result(title):
    return SearchResult(
        title=title, size=1, seeders=1, leechers=0, source="t",
        category=Category.MOVIES, download_url=f"magnet:?xt=urn:btih:{title}",
    )


class CountingIndexer:
    def __init__(self, name, error=None):
        self.name = name
        self.enabled = True
        self.calls = 0
        self._error = error

    async def search(self, query, category):
        self.calls += 1
        if self._error:
            raise self._error
        return [_result(f"{self.name}-{query}")]


async def test_service_pauses_tracker_after_rate_limit():
    limited = CountingIndexer("a", error=RateLimited(300))
    throttles: dict[str, TrackerThrottle] = {}
    service = SearchService([limited], throttles=throttles, min_interval=0.0)
    assert await service.search("x") == []
    assert await service.search("x") == []
    assert limited.calls == 1  # second search skipped while paused
    assert throttles["a"].is_blocked()


async def test_service_reuses_shared_throttles():
    throttles: dict[str, TrackerThrottle] = {}
    a = CountingIndexer("a")
    SearchService([a], throttles=throttles, min_interval=1.0)
    first = throttles.get("a")
    SearchService([a], throttles=throttles, min_interval=3.0)
    assert throttles["a"] is first
    assert first is not None and first.min_interval == 3.0


async def test_service_recent_queries_with_empty_text():
    a = CountingIndexer("a")
    service = SearchService([a])
    out = await service.recent()
    assert [r.title for r in out] == ["a-"]
