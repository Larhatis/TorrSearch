from __future__ import annotations

import logging

import httpx

from torsearch.config import JellyfinConfig

logger = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self, config: JellyfinConfig, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self._url = config.url.rstrip("/")
        self._api_key = config.api_key
        self._client = client
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._api_key)

    @property
    def base_url(self) -> str:
        return self._url

    async def owned(self) -> dict[str, str]:
        if not self.enabled:
            return {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._url}/Items",
                params={
                    "Recursive": "true", "IncludeItemTypes": "Movie,Series",
                    "Fields": "ProviderIds", "api_key": self._api_key,
                },
            )
            response.raise_for_status()
            result: dict[str, str] = {}
            for item in response.json().get("Items", []):
                tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
                if not tmdb:
                    continue
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                result[f"{media_type}:{tmdb}"] = item.get("Id", "")
            return result
        except Exception as exc:  # resilience: never raise to the web layer
            logger.warning("Jellyfin owned() failed: %s", exc)
            return {}
        finally:
            if owns_client:
                await client.aclose()
