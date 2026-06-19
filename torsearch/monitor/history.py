from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class MonitorRecord(BaseModel):
    search: str
    title: str
    source: str
    infohash: str | None = None
    download_url: str
    kind: str  # "grabbed" | "found"
    at: datetime


class MonitorHistory:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[MonitorRecord]:
        if not self._path.exists():
            return []
        return [MonitorRecord.model_validate(item) for item in json.loads(self._path.read_text())]

    def records(self) -> list[MonitorRecord]:
        return list(reversed(self._load()))

    def seen_keys(self, search_name: str) -> set[str]:
        return {
            r.infohash or r.download_url
            for r in self._load()
            if r.search == search_name
        }

    def add(self, record: MonitorRecord) -> None:
        existing = self._load()
        existing.append(record)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([r.model_dump(mode="json") for r in existing], indent=2))
        os.replace(tmp, self._path)
