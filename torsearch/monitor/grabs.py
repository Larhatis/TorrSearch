from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from torsearch.db.database import Collection, Database, as_collection
from torsearch.monitor.history import MonitorRecord

AUTO = "auto"
MANUAL = "manual"


class GrabRecord(BaseModel):
    info_hash: str
    title: str
    origin: str  # AUTO (chosen by the surveillance) | MANUAL (sent by a user)
    target: str = ""  # "movie:<id>", "tv:<id>", "saved:<name>" or ""
    added_at: datetime


def added_hash(added: object) -> str:
    """The lowercase infohash Transmission answered to an add, or "" when it gave none."""
    return str(getattr(added, "info_hash", "") or "").lower()


class GrabRegistry:
    """Which torrents TorrSearch sent to Transmission, keyed by infohash, and who chose them.

    The stalled-torrent purge deletes data: it only ever touches torrents recorded here as
    chosen by the surveillance, never a torrent added by hand (in Transmission or here).
    """

    def __init__(self, source: Collection | Database | str | Path):
        self._c = as_collection(source, "grabs")

    def record(self, info_hash: str | None, title: str, origin: str, target: str = "",
               at: datetime | None = None) -> None:
        key = (info_hash or "").strip().lower()
        if not key:
            return  # an entry nobody can match later is worse than none
        existing = self.get(key)
        if existing is not None and existing.origin == MANUAL:
            return  # a release a user picked stays theirs, whatever the surveillance does next
        record = GrabRecord(info_hash=key, title=title, origin=origin, target=target,
                            added_at=at or datetime.now(UTC))
        self._c.upsert(key, record.model_dump(mode="json"))

    def get(self, info_hash: str) -> GrabRecord | None:
        data = self._c.get(info_hash.strip().lower())
        return GrabRecord.model_validate(data) if data else None

    def is_auto(self, info_hash: str | None) -> bool:
        if not info_hash:
            return False
        record = self.get(info_hash)
        return record is not None and record.origin == AUTO

    def forget(self, info_hash: str) -> None:
        self._c.delete(info_hash.strip().lower())

    def seed_from_history(self, records: list[MonitorRecord]) -> int:
        """First start with a registry: adopt the surveillance grabs the history still knows."""
        if not self._c.is_empty():
            return 0
        seeded = 0
        for r in records:
            if r.kind != "grabbed" or not r.infohash or r.source == "manuel":
                continue
            self.record(r.infohash, r.title, AUTO, at=r.at)
            seeded += 1
        return seeded
