from __future__ import annotations

import json
import os
from pathlib import Path

from torsearch.models import WantedSeries


class SeriesLibrary:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[WantedSeries]:
        if not self._path.exists():
            return []
        return [WantedSeries.model_validate(item) for item in json.loads(self._path.read_text())]

    def _save(self, items: list[WantedSeries]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([s.model_dump(mode="json") for s in items], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[WantedSeries]:
        return self._load()

    def add(self, series: WantedSeries) -> bool:
        items = self._load()
        if any(s.tmdb_id == series.tmdb_id for s in items):
            return False
        items.append(series)
        self._save(items)
        return True

    def remove(self, tmdb_id: int) -> None:
        self._save([s for s in self._load() if s.tmdb_id != tmdb_id])

    def mark_grabbed(self, tmdb_id: int, keys: list[str]) -> None:  # type: ignore[valid-type]  # `list` method shadows builtin
        items = self._load()
        for i, s in enumerate(items):
            if s.tmdb_id == tmdb_id:
                merged = sorted(set(s.grabbed) | set(keys))
                items[i] = s.model_copy(update={"grabbed": merged})
        self._save(items)
