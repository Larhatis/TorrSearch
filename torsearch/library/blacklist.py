from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from torsearch.db.database import Collection, Database, as_collection


class BlacklistRecord(BaseModel):
    key: str
    infohash: str | None = None
    title: str = ""
    reason: str = "failed"
    blacklisted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Blacklist:
    def __init__(self, source: Collection | Database | str | Path):
        self._c = as_collection(source, "blacklist")

    def add(self, infohash: str | None, title: str, reason: str = "failed") -> None:
        norm_hash = infohash.lower().strip() if infohash else None
        norm_title = title.lower().strip()
        record = BlacklistRecord(
            key=f"hash:{norm_hash}" if norm_hash else f"title:{norm_title}",
            infohash=norm_hash,
            title=title,
            reason=reason,
            blacklisted_at=datetime.now(UTC),
        )
        dump = record.model_dump(mode="json")
        if norm_hash:
            self._c.upsert(f"hash:{norm_hash}", dump)
        if norm_title:
            self._c.upsert(f"title:{norm_title}", dump)

    def is_blacklisted(self, infohash: str | None, title: str) -> bool:
        if infohash:
            norm_hash = infohash.lower().strip()
            if self._c.get(f"hash:{norm_hash}") is not None:
                return True
        norm_title = f"title:{title.lower().strip()}"
        return self._c.get(norm_title) is not None

    def remove(self, key_or_hash_or_title: str) -> None:
        norm = key_or_hash_or_title.lower().strip()
        data = self._c.get(norm) or self._c.get(f"hash:{norm}") or self._c.get(f"title:{norm}")
        if data:
            rec = BlacklistRecord.model_validate(data)
            if rec.infohash:
                self._c.delete(f"hash:{rec.infohash}")
            if rec.title:
                self._c.delete(f"title:{rec.title.lower().strip()}")
        else:
            self._c.delete(norm)
            self._c.delete(f"hash:{norm}")
            self._c.delete(f"title:{norm}")

    def list(self) -> list[BlacklistRecord]:
        seen_keys: set[str] = set()
        records: list[BlacklistRecord] = []
        for d in self._c.all():
            rec = BlacklistRecord.model_validate(d)
            uid = rec.infohash or rec.title.lower().strip()
            if uid not in seen_keys:
                seen_keys.add(uid)
                records.append(rec)
        return records
