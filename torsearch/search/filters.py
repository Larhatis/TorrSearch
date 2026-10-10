from __future__ import annotations

import re

from pydantic import BaseModel, Field

from torsearch.models import SearchResult
from torsearch.search.relevance import compute_relevance

_QUALITY_PATTERNS = [
    ("2160p", re.compile(r"\b(2160p|4k|uhd)\b", re.IGNORECASE)),
    ("1080p", re.compile(r"\b1080p\b", re.IGNORECASE)),
    ("720p", re.compile(r"\b720p\b", re.IGNORECASE)),
    ("480p", re.compile(r"\b(480p|sd)\b", re.IGNORECASE)),
]

VALID_SORTS = {"relevance", "seeders", "size", "date", "title", "leechers"}
VALID_DIRECTIONS = {"asc", "desc"}


def detect_quality(title: str) -> str:
    for label, pattern in _QUALITY_PATTERNS:
        if pattern.search(title):
            return label
    return "other"


def quality_rank(title: str) -> int:
    """Rank of a title's quality (0 = best, higher = worse; "other" is last)."""
    label = detect_quality(title)
    for i, (lbl, _) in enumerate(_QUALITY_PATTERNS):
        if lbl == label:
            return i
    return len(_QUALITY_PATTERNS)


class ResultFilters(BaseModel):
    min_seeders: int = 0
    min_size: int | None = None
    max_size: int | None = None
    qualities: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    sort: str = "relevance"
    direction: str = "desc"
    query: str = ""


_SORT_KEYS = {
    "title": lambda r: r.title.lower(),
    "size": lambda r: r.size,
    "seeders": lambda r: r.seeders,
    "leechers": lambda r: r.leechers,
    "date": lambda r: r.publish_date.timestamp() if r.publish_date else 0.0,
}


def apply(results: list[SearchResult], filters: ResultFilters) -> list[SearchResult]:
    excluded = [w.lower() for w in filters.exclude if w]
    kept: list[SearchResult] = []
    for r in results:
        if r.seeders < filters.min_seeders:
            continue
        if filters.min_size is not None and r.size < filters.min_size:
            continue
        if filters.max_size is not None and r.size > filters.max_size:
            continue
        if filters.qualities and detect_quality(r.title) not in filters.qualities:
            continue
        title_lower = r.title.lower()
        if any(word in title_lower for word in excluded):
            continue
        kept.append(r)

    sort = filters.sort if filters.sort in VALID_SORTS else "relevance"
    direction = filters.direction if filters.direction in VALID_DIRECTIONS else "desc"
    rev = (direction == "desc")

    if sort == "relevance":
        q = filters.query.strip()
        if q:
            kept.sort(key=lambda r: (compute_relevance(r, q), r.seeders), reverse=rev)
        else:
            kept.sort(key=lambda r: r.seeders, reverse=rev)
    elif sort == "seeders":
        q = filters.query.strip()
        if q:
            kept.sort(key=lambda r: (r.seeders, compute_relevance(r, q)), reverse=rev)
        else:
            kept.sort(key=lambda r: r.seeders, reverse=rev)
    else:
        kept.sort(key=_SORT_KEYS[sort], reverse=rev)
    return kept
