from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from torsearch.config import JellyfinConfig
from torsearch.parser.release import parse_release
from torsearch.redact import redact
from torsearch.search.matcher import match_media_title, normalize_title

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JellyfinItem:
    id: str
    name: str
    media_type: str  # "movie" | "tv"
    year: int | None = None
    tmdb_id: str | None = None


class JellyfinClient:
    def __init__(self, config: JellyfinConfig, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self._url = config.url.rstrip("/")
        self._api_key = config.api_key
        self._client = client
        self._timeout = timeout
        self._items_cache: tuple[float, list[JellyfinItem]] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._api_key)

    @property
    def base_url(self) -> str:
        return self._url

    def _auth(self) -> dict[str, str]:
        # Jellyfin 12 dropped the legacy ``api_key`` query parameter: the key goes in the
        # MediaBrowser Authorization header (supported by 10.x too, and kept out of URLs/logs).
        return {"Authorization": f'MediaBrowser Token="{self._api_key}"'}

    async def get_items(self) -> list[JellyfinItem]:
        if not self.enabled:
            return []
        now = time.monotonic()
        if self._items_cache is not None:
            ts, cached_items = self._items_cache
            if now - ts < 30.0:
                return cached_items
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._url}/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie,Series",
                    "Fields": "ProviderIds,ProductionYear",
                },
                headers=self._auth(),
            )
            response.raise_for_status()
            items: list[JellyfinItem] = []
            for item in response.json().get("Items", []):
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
                year = item.get("ProductionYear")
                items.append(
                    JellyfinItem(
                        id=item.get("Id", ""),
                        name=item.get("Name", ""),
                        media_type=media_type,
                        year=int(year) if year else None,
                        tmdb_id=str(tmdb) if tmdb else None,
                    )
                )
            self._items_cache = (now, items)
            return items
        except Exception as exc:  # resilience: never raise to the web layer
            logger.warning("Jellyfin get_items() failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def owned(self) -> dict[str, str]:
        items = await self.get_items()
        return {f"{item.media_type}:{item.tmdb_id}": item.id for item in items if item.tmdb_id}

    async def find_matching(self, query: str) -> JellyfinItem | None:
        if not self.enabled or not query.strip():
            return None
        items = await self.get_items()
        if not items:
            return None

        parsed = parse_release(query)
        target = parsed.clean_title if parsed.clean_title else query.strip()
        target_norm = normalize_title(target)
        if not target_norm:
            return None

        # 1. Exact match on normalized title
        for item in items:
            item_norm = normalize_title(item.name)
            if item_norm == target_norm:
                if parsed.year is not None and item.year is not None:
                    if abs(parsed.year - item.year) > 1:
                        continue
                return item

        # 2. Match with match_media_title
        for item in items:
            is_series = item.media_type == "tv"
            if match_media_title(parsed, target_title=item.name, target_year=item.year, is_series=is_series):
                return item

        return None

    async def refresh(self) -> bool:
        """Trigger a full Jellyfin library scan. Best-effort: never raises."""
        if not self.enabled:
            return False
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(f"{self._url}/Library/Refresh", headers=self._auth())
            response.raise_for_status()
            return True
        except Exception as exc:  # resilience: never raise
            logger.warning("Jellyfin refresh() failed: %s", exc)
            return False
        finally:
            if owns_client:
                await client.aclose()

    async def episodes(self, item_id: str) -> set[str]:
        """Episode keys (e.g. ``S01E02``) physically present for a series item."""
        if not self.enabled or not item_id:
            return set()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(f"{self._url}/Shows/{item_id}/Episodes", headers=self._auth())
            response.raise_for_status()
            keys: set[str] = set()
            for item in response.json().get("Items", []):
                season = item.get("ParentIndexNumber")
                episode = item.get("IndexNumber")
                if season is None or episode is None:
                    continue
                keys.add(f"S{int(season):02d}E{int(episode):02d}")
            return keys
        except Exception as exc:  # resilience: never raise
            logger.warning("Jellyfin episodes() failed: %s", exc)
            return set()
        finally:
            if owns_client:
                await client.aclose()

    async def test(self) -> tuple[bool, str]:
        """Connection check for the status panel: never raises, never echoes the key."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(f"{self._url}/System/Info", headers=self._auth())
            if response.status_code in (401, 403):
                return False, "Clé API refusée (401/403)."
            response.raise_for_status()
            info = response.json()
            return True, f"{info.get('ServerName', '?')} · Jellyfin {info.get('Version', '?')}"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.ConnectError:
            return False, "Serveur injoignable (adresse introuvable ou connexion refusée)."
        except httpx.HTTPStatusError as exc:
            return False, f"Erreur HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {redact(str(exc))}."
        except ValueError:
            return False, "Réponse inattendue (pas un serveur Jellyfin ?)."
        finally:
            if owns_client:
                await client.aclose()
