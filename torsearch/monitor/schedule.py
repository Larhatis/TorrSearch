from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from torsearch.db.database import Collection

# The RSS feed catches new releases every cycle; targeted searches only hunt the backlog,
# so they run far less often (tracker-friendly), more often while a gap is fresh.
SAVED_SEARCH_INTERVAL = timedelta(hours=6)
_NEW_MOVIE_DAYS = 7
_FRESH_EPISODE_DAYS = 2
_RECENT_EPISODE_DAYS = 14


class SearchSchedule:
    """When each watched item (``movie:<id>``, ``tv:<id>``, ``saved:<name>``) was last
    searched on the trackers. Persisted when given a collection, in memory otherwise."""

    def __init__(self, collection: Collection | None = None):
        self._c = collection
        self._mem: dict[str, datetime] = {}

    def last(self, key: str) -> datetime | None:
        if self._c is None:
            return self._mem.get(key)
        data = self._c.get(key)
        if not data:
            return None
        at = datetime.fromisoformat(data["at"])
        return at if at.tzinfo else at.replace(tzinfo=UTC)

    def mark(self, key: str, at: datetime) -> None:
        if self._c is None:
            self._mem[key] = at
        else:
            self._c.upsert(key, {"at": at.isoformat()})

    def is_due(self, key: str, interval: timedelta, now: datetime) -> bool:
        last = self.last(key)
        return last is None or now - last >= interval


def movie_interval(movie, now: datetime) -> timedelta:
    added = movie.added_at if movie.added_at.tzinfo else movie.added_at.replace(tzinfo=UTC)
    if now - added < timedelta(days=_NEW_MOVIE_DAYS):
        return timedelta(hours=6)
    return timedelta(hours=24)


def series_interval(missing_air_dates: Iterable[str | None], today: date) -> timedelta:
    """Search often while a missing episode is fresh, then back off."""
    ages: list[int] = []
    for value in missing_air_dates:
        if not value:
            continue
        try:
            ages.append((today - date.fromisoformat(value)).days)
        except ValueError:
            continue
    if not ages:
        return timedelta(hours=6)
    youngest = min(ages)
    if youngest <= _FRESH_EPISODE_DAYS:
        return timedelta(hours=1)
    if youngest <= _RECENT_EPISODE_DAYS:
        return timedelta(hours=6)
    return timedelta(hours=24)
