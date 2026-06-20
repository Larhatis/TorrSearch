from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from torsearch.models import WantedMovie


class MovieLibrary:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[WantedMovie]:
        if not self._path.exists():
            return []
        return [WantedMovie.model_validate(item) for item in json.loads(self._path.read_text())]

    def _save(self, movies: list[WantedMovie]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([m.model_dump(mode="json") for m in movies], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[WantedMovie]:
        return self._load()

    def wanted(self) -> list[WantedMovie]:
        return [m for m in self._load() if m.status == "wanted"]

    def add(self, movie: WantedMovie) -> bool:
        movies = self._load()
        if any(m.tmdb_id == movie.tmdb_id for m in movies):
            return False
        movies.append(movie)
        self._save(movies)
        return True

    def remove(self, tmdb_id: int) -> None:
        self._save([m for m in self._load() if m.tmdb_id != tmdb_id])

    def mark_grabbed(self, tmdb_id: int, grabbed_title: str, at: datetime) -> None:
        movies = self._load()
        for i, m in enumerate(movies):
            if m.tmdb_id == tmdb_id:
                movies[i] = m.model_copy(
                    update={"status": "grabbed", "grabbed_title": grabbed_title, "grabbed_at": at}
                )
        self._save(movies)
