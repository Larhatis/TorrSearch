from __future__ import annotations

import logging

import httpx

from torsearch.config import MetadataConfig
from torsearch.models import MediaResult

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
_TRENDING_URL = "https://api.themoviedb.org/3/trending/all/week"


def parse_multi(payload: dict) -> list[MediaResult]:
    out: list[MediaResult] = []
    for item in payload.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        if item.get("id") is None:
            continue
        title = item.get("title") or item.get("name") or ""
        date = item.get("release_date") or item.get("first_air_date") or ""
        out.append(
            MediaResult(
                tmdb_id=int(item["id"]),
                media_type=media_type,
                title=title,
                year=date[:4] if date else None,
                overview=item.get("overview") or "",
                poster_path=item.get("poster_path"),
            )
        )
    return out


class TmdbClient:
    def __init__(
        self,
        config: MetadataConfig,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        self._api_key = config.tmdb_api_key
        self._client = client
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[MediaResult]:
        if not self.enabled or not query.strip():
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                _SEARCH_URL,
                params={
                    "api_key": self._api_key,
                    "query": query,
                    "language": "fr-FR",
                    "include_adult": "false",
                },
            )
            response.raise_for_status()
            return parse_multi(response.json())
        except Exception as exc:  # resilience: never raise to the web layer
            logger.warning("TMDB search failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def trending(self) -> list[MediaResult]:
        if not self.enabled:
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                _TRENDING_URL, params={"api_key": self._api_key, "language": "fr-FR"}
            )
            response.raise_for_status()
            return parse_multi(response.json())
        except Exception as exc:  # resilience
            logger.warning("TMDB trending failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()
