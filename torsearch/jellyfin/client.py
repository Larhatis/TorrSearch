from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from torsearch.config import JellyfinConfig
from torsearch.parser.release import parse_release
from torsearch.redact import redact
from torsearch.search.matcher import match_media_title, normalize_title, strip_articles

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JellyfinItem:
    id: str
    name: str
    media_type: str  # "movie" | "tv"
    year: int | None = None
    tmdb_id: str | None = None
    original_title: str | None = None


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
                    "Fields": "ProviderIds,ProductionYear,OriginalTitle",
                    "Limit": "10000",
                },
                headers=self._auth(),
            )
            response.raise_for_status()
            items: list[JellyfinItem] = []
            for item in response.json().get("Items", []):
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
                year = item.get("ProductionYear")
                orig = item.get("OriginalTitle")
                items.append(
                    JellyfinItem(
                        id=item.get("Id", ""),
                        name=item.get("Name", ""),
                        media_type=media_type,
                        year=int(year) if year else None,
                        tmdb_id=str(tmdb) if tmdb else None,
                        original_title=str(orig) if orig else None,
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

    async def search_items(self, term: str, limit: int = 50) -> list[JellyfinItem]:
        """Search Jellyfin server directly with searchTerm across the entire library."""
        if not self.enabled or not term.strip():
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._url}/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie,Series",
                    "searchTerm": term.strip(),
                    "Fields": "ProviderIds,ProductionYear,OriginalTitle",
                    "Limit": str(limit),
                },
                headers=self._auth(),
            )
            response.raise_for_status()
            items: list[JellyfinItem] = []
            for item in response.json().get("Items", []):
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
                year = item.get("ProductionYear")
                orig = item.get("OriginalTitle")
                items.append(
                    JellyfinItem(
                        id=item.get("Id", ""),
                        name=item.get("Name", ""),
                        media_type=media_type,
                        year=int(year) if year else None,
                        tmdb_id=str(tmdb) if tmdb else None,
                        original_title=str(orig) if orig else None,
                    )
                )
            return items
        except Exception as exc:  # resilience: never raise
            logger.warning("Jellyfin search_items(%s) failed: %s", term, exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def owned(self) -> dict[str, str]:
        items = await self.get_items()
        return {f"{item.media_type}:{item.tmdb_id}": item.id for item in items if item.tmdb_id}

    async def find_matches(self, query: str, limit: int = 6) -> list[JellyfinItem]:
        if not self.enabled or not query.strip():
            return []

        parsed = parse_release(query)
        target = parsed.clean_title if parsed.clean_title else query.strip()
        target_norm = normalize_title(target)
        if not target_norm:
            return []

        # 1. Search server-side directly with searchTerm (bypasses any 100-item pagination limit)
        server_items = await self.search_items(target, limit=50)
        # 2. Also retrieve items from local cache/library
        cached_items = await self.get_items()

        combined: dict[str, JellyfinItem] = {it.id: it for it in cached_items}
        for it in server_items:
            combined[it.id] = it
        items = list(combined.values())
        if not items:
            return []

        _STOP_WORDS = {"the", "le", "la", "les", "un", "une", "des", "of", "du", "de", "and", "et"}
        tokens = [w for w in target_norm.split() if w]
        sig_tokens = [w for w in tokens if w not in _STOP_WORDS] or tokens

        scored_items: list[tuple[int, int, str, JellyfinItem]] = []
        target_no_art = strip_articles(target_norm)

        for item in items:
            item_norm = normalize_title(item.name)
            item_orig_norm = normalize_title(item.original_title) if item.original_title else ""
            if not item_norm and not item_orig_norm:
                continue

            item_no_art = strip_articles(item_norm) if item_norm else ""
            item_orig_no_art = strip_articles(item_orig_norm) if item_orig_norm else ""
            item_words = set(item_norm.split()) | (set(item_orig_norm.split()) if item_orig_norm else set())

            year_matches = False
            if parsed.year is not None and item.year is not None:
                year_matches = abs(parsed.year - item.year) <= 1

            priority = 0

            # Tier 1: Exact title match (on name or original title)
            if item_norm == target_norm or item_orig_norm == target_norm:
                if parsed.year is not None:
                    priority = 100 if year_matches else 85
                else:
                    priority = 95
            elif item_no_art == target_no_art or (bool(item_orig_no_art) and item_orig_no_art == target_no_art):
                if parsed.year is not None:
                    priority = 92 if year_matches else 82
                else:
                    priority = 88
            # Tier 2: match_media_title
            elif match_media_title(
                parsed,
                target_title=item.name,
                target_original_title=item.original_title,
                target_year=item.year,
                is_series=(item.media_type == "tv"),
            ):
                priority = 80
            # Tier 3: Keyword / franchise containment (only if search is at least 3 chars)
            elif len(target_norm) >= 3 and all(t in item_words for t in sig_tokens):
                if parsed.year is not None and year_matches:
                    priority = 70
                else:
                    priority = 50

            if priority > 0:
                item_year = item.year or 0
                scored_items.append((priority, item_year, item.name, item))

        # Sort: highest priority first, then newest year first, then title
        scored_items.sort(key=lambda x: (-x[0], -x[1], x[2]))

        # Deduplicate by item ID preserving order
        seen_ids: set[str] = set()
        results: list[JellyfinItem] = []
        for _, _, _, item in scored_items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                results.append(item)
                if len(results) >= limit:
                    break

        return results

    async def find_matching(self, query: str) -> JellyfinItem | None:
        matches = await self.find_matches(query, limit=1)
        return matches[0] if matches else None

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
