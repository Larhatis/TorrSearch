from __future__ import annotations

import time
from collections import deque


class HourlyLimit:
    """At most ``max_calls`` per sliding window (one hour by default), kept in memory."""

    def __init__(self, max_calls: int, window_seconds: float = 3600, clock=time.monotonic):
        self._max = max_calls
        self._window = window_seconds
        self._clock = clock
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        """Record a call if the limit allows it; False (nothing recorded) otherwise."""
        now = self._clock()
        while self._calls and now - self._calls[0] >= self._window:
            self._calls.popleft()
        if len(self._calls) >= self._max:
            return False
        self._calls.append(now)
        return True
