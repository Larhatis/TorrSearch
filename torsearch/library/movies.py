from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from torsearch.db.database import Collection, as_collection
from torsearch.models import WantedMovie


class MovieLibrary:
    def __init__(self, source: Collection | str | Path, migrate_from: str | Path | None = None):
        self._c = as_collection(source, "movies")
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        if not path.exists() or not self._c.is_empty():
            return
        try:
            items = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.replace_all([(str(m["tmdb_id"]), m) for m in items if "tmdb_id" in m])

    def list(self) -> list[WantedMovie]:
        return [WantedMovie.model_validate(d) for d in self._c.all()]

    def wanted(self) -> list[WantedMovie]:  # type: ignore[valid-type]  # `list` method shadows builtin
        return [m for m in self.list() if m.status == "wanted"]

    def add(self, movie: WantedMovie) -> bool:
        if self._c.get(str(movie.tmdb_id)) is not None:
            return False
        self._c.upsert(str(movie.tmdb_id), movie.model_dump(mode="json"))
        return True

    def remove(self, tmdb_id: int) -> None:
        self._c.delete(str(tmdb_id))

    def mark_grabbed(self, tmdb_id: int, grabbed_title: str, at: datetime) -> None:
        data = self._c.get(str(tmdb_id))
        if data is None:
            return
        movie = WantedMovie.model_validate(data).model_copy(
            update={"status": "grabbed", "grabbed_title": grabbed_title, "grabbed_at": at}
        )
        self._c.upsert(str(tmdb_id), movie.model_dump(mode="json"))
