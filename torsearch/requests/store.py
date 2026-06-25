from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from torsearch.db.database import Collection, as_collection


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
    def __init__(self, source: Collection | str | Path, migrate_from: str | Path | None = None):
        self._c = as_collection(source, "requests")
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        if not path.exists() or not self._c.is_empty():
            return
        try:
            items = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.replace_all([(r["id"], r) for r in items if r.get("id")])

    def _all(self) -> list[MediaRequest]:
        return [MediaRequest.model_validate(d) for d in self._c.all()]

    def list(self) -> list[MediaRequest]:
        return list(reversed(self._all()))

    def pending(self) -> list[MediaRequest]:  # type: ignore[valid-type]  # `list` method shadows builtin
        return [r for r in self.list() if r.status == RequestStatus.PENDING]

    def for_user(self, username: str) -> list[MediaRequest]:  # type: ignore[valid-type]
        return [r for r in self.list() if r.username == username]

    def count_pending(self) -> int:
        return sum(1 for r in self._all() if r.status == RequestStatus.PENDING)

    def get(self, request_id: str) -> MediaRequest | None:
        data = self._c.get(request_id)
        return MediaRequest.model_validate(data) if data else None

    def add(self, username: str, media_type: str, tmdb_id: int, title: str,
            year: str | None, poster_path: str | None) -> MediaRequest:
        existing = next(
            (r for r in self._all()
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
        self._c.upsert(request.id, request.model_dump(mode="json"))
        return request

    def set_status(self, request_id: str, status: RequestStatus,
                   decided_by: str) -> MediaRequest | None:
        current = self.get(request_id)
        if current is None:
            return None
        updated = current.model_copy(update={
            "status": status, "decided_at": datetime.now(UTC), "decided_by": decided_by,
        })
        self._c.upsert(request_id, updated.model_dump(mode="json"))
        return updated
