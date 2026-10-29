from __future__ import annotations

import asyncio
import time


class TrackerThrottle:
    """Per-tracker politeness: one request at a time, spaced by ``min_interval`` seconds.

    ``block()`` pauses the tracker entirely (e.g. after an HTTP 429) until the delay expires.
    The instance outlives settings changes (kept by ``AppContext``) so the spacing holds
    across client rebuilds.
    """

    def __init__(self, min_interval: float = 2.0, clock=time.monotonic, sleep=asyncio.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_done: float | None = None
        self._blocked_until = 0.0

    def is_blocked(self) -> bool:
        return self._clock() < self._blocked_until

    def block(self, seconds: float) -> None:
        self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    async def __aenter__(self) -> TrackerThrottle:
        await self._lock.acquire()
        if self._last_done is not None:
            wait = self._last_done + self.min_interval - self._clock()
            if wait > 0:
                await self._sleep(wait)
        return self

    async def __aexit__(self, *exc) -> None:
        self._last_done = self._clock()
        self._lock.release()
