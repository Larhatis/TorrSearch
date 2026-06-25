from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from torsearch.db.database import Collection, as_collection


class MonitorRecord(BaseModel):
    search: str
    title: str
    source: str
    infohash: str | None = None
    download_url: str
    kind: str  # "grabbed" | "found"
    at: datetime


class MonitorHistory:
    def __init__(self, source: Collection | str | Path, max_records: int = 1000,
                 migrate_from: str | Path | None = None):
        self._c = as_collection(source, "monitor")
        self._max_records = max_records
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        if not path.exists() or not self._c.is_empty():
            return
        try:
            items = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.replace_all([(uuid.uuid4().hex, r) for r in items])

    def _all(self) -> list[MonitorRecord]:
        return [MonitorRecord.model_validate(d) for d in self._c.all()]

    def records(self) -> list[MonitorRecord]:
        return list(reversed(self._all()))

    def seen_keys(self, search_name: str) -> set[str]:
        return {
            r.infohash or r.download_url
            for r in self._all()
            if r.search == search_name
        }

    def add(self, record: MonitorRecord) -> None:
        self._c.upsert(uuid.uuid4().hex, record.model_dump(mode="json"))
        if self._max_records:
            self._c.trim(self._max_records)
