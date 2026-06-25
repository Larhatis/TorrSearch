from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MediaRequest(BaseModel):
    id: str
    username: str
    media_type: str  # "movie" | "tv"
    tmdb_id: int
    title: str
    year: str | None = None
    poster_path: str | None = None
    status: RequestStatus = RequestStatus.PENDING
    requested_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None


class RequestStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[MediaRequest]:
        if not self._path.exists():
            return []
        return [MediaRequest.model_validate(r) for r in json.loads(self._path.read_text())]

    def _save(self, items: list[MediaRequest]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([r.model_dump(mode="json") for r in items], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[MediaRequest]:
        return list(reversed(self._load()))

    def pending(self) -> list[MediaRequest]:  # type: ignore[valid-type]  # `list` method shadows builtin
        return [r for r in self.list() if r.status == RequestStatus.PENDING]

    def for_user(self, username: str) -> list[MediaRequest]:  # type: ignore[valid-type]
        return [r for r in self.list() if r.username == username]

    def count_pending(self) -> int:
        return sum(1 for r in self._load() if r.status == RequestStatus.PENDING)

    def get(self, request_id: str) -> MediaRequest | None:
        return next((r for r in self._load() if r.id == request_id), None)

    def add(self, username: str, media_type: str, tmdb_id: int, title: str,
            year: str | None, poster_path: str | None) -> MediaRequest:
        items = self._load()
        existing = next(
            (r for r in items
             if r.status == RequestStatus.PENDING
             and r.media_type == media_type and r.tmdb_id == tmdb_id),
            None,
        )
        if existing is not None:
            return existing
        request = MediaRequest(
            id=uuid.uuid4().hex, username=username, media_type=media_type,
            tmdb_id=tmdb_id, title=title, year=year, poster_path=poster_path,
            requested_at=datetime.now(UTC),
        )
        items.append(request)
        self._save(items)
        return request

    def set_status(self, request_id: str, status: RequestStatus,
                   decided_by: str) -> MediaRequest | None:
        items = self._load()
        updated: MediaRequest | None = None
        for i, r in enumerate(items):
            if r.id == request_id:
                updated = r.model_copy(update={
                    "status": status,
                    "decided_at": datetime.now(UTC),
                    "decided_by": decided_by,
                })
                items[i] = updated
        if updated is not None:
            self._save(items)
        return updated
