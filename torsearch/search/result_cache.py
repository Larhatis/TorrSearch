from __future__ import annotations

import secrets
import time
from collections import OrderedDict

from torsearch.models import SearchResult


class ResultCache:
    """Search results kept server-side, so the browser only gets an opaque id.

    A tracker download URL embeds the user's passkey: members must be able to send a
    result to Transmission without ever seeing (or copying) that URL. Ids expire with the
    entry; the cache is bounded.
    """

    def __init__(self, ttl_seconds: float = 6 * 3600, max_items: int = 5000, clock=time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_items
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, SearchResult]] = OrderedDict()
        self._by_url: dict[str, str] = {}

    def put(self, result: SearchResult) -> str:
        known = self._by_url.get(result.download_url)
        if known is not None and self.get(known) is not None:
            self._items[known] = (self._clock() + self._ttl, result)
            self._items.move_to_end(known)
            return known
        rid = secrets.token_urlsafe(16)
        self._items[rid] = (self._clock() + self._ttl, result)
        self._by_url[result.download_url] = rid
        while len(self._items) > self._max:
            old_id, (_, old) = self._items.popitem(last=False)
            if self._by_url.get(old.download_url) == old_id:
                del self._by_url[old.download_url]
        return rid

    def get(self, rid: str) -> SearchResult | None:
        entry = self._items.get(rid)
        if entry is None:
            return None
        expires, result = entry
        if expires <= self._clock():
            del self._items[rid]
            if self._by_url.get(result.download_url) == rid:
                del self._by_url[result.download_url]
            return None
        return result
