from __future__ import annotations

import json
from pathlib import Path

from torsearch.db.database import Collection, as_collection
from torsearch.models import WantedSeries


class SeriesLibrary:
    def __init__(self, source: Collection | str | Path, migrate_from: str | Path | None = None):
        self._c = as_collection(source, "series")
        if migrate_from is not None:
            self._migrate(Path(migrate_from))

    def _migrate(self, path: Path) -> None:
        if not path.exists() or not self._c.is_empty():
            return
        try:
            items = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        self._c.replace_all([(str(s["tmdb_id"]), s) for s in items if "tmdb_id" in s])

    def list(self) -> list[WantedSeries]:
        return [WantedSeries.model_validate(d) for d in self._c.all()]

    def add(self, series: WantedSeries) -> bool:
        if self._c.get(str(series.tmdb_id)) is not None:
            return False
        self._c.upsert(str(series.tmdb_id), series.model_dump(mode="json"))
        return True

    def remove(self, tmdb_id: int) -> None:
        self._c.delete(str(tmdb_id))

    def mark_grabbed(self, tmdb_id: int, keys: list[str]) -> None:  # type: ignore[valid-type]  # `list` method shadows builtin
        data = self._c.get(str(tmdb_id))
        if data is None:
            return
        series = WantedSeries.model_validate(data)
        merged = sorted(set(series.grabbed) | set(keys))
        self._c.upsert(str(tmdb_id), series.model_copy(update={"grabbed": merged}).model_dump(mode="json"))
