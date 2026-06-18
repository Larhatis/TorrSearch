from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, computed_field


class Category(str, Enum):
    ALL = "all"
    MOVIES = "movies"
    TV = "tv"
    ANIME = "anime"
    OTHER = "other"


class SearchResult(BaseModel):
    title: str
    size: int
    seeders: int
    leechers: int
    source: str
    category: Category
    download_url: str
    info_url: str | None = None
    publish_date: datetime | None = None
    infohash: str | None = None

    @computed_field
    @property
    def is_magnet(self) -> bool:
        return self.download_url.startswith("magnet:")
