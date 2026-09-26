import asyncio
import logging
import time
from datetime import date

import httpx

from torsearch.config import MetadataConfig
from torsearch.models import EpisodeInfo, MediaResult, SeasonInfo
from torsearch.redact import redact

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
_TRENDING_URL = "https://api.themoviedb.org/3/trending/all/week"
_TV_URL = "https://api.themoviedb.org/3/tv"
_CONFIG_URL = "https://api.themoviedb.org/3/configuration"


def parse_multi(payload: dict, default_type: str | None = None) -> list[MediaResult]:
    out: list[MediaResult] = []
    for item in payload.get("results", []):
        media_type = item.get("media_type") or default_type
        if media_type not in ("movie", "tv"):
            continue
        if item.get("id") is None:
            continue
        title = item.get("title") or item.get("name") or ""
        original_title = item.get("original_title") or item.get("original_name") or None
        date = item.get("release_date") or item.get("first_air_date") or ""
        out.append(
            MediaResult(
                tmdb_id=int(item["id"]),
                media_type=media_type,
                title=title,
                original_title=original_title,
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
        episode_cache_seconds: float = 6 * 3600,
        clock=time.monotonic,
    ):
        self._api_key = config.tmdb_api_key
        self._client = client
        self._timeout = timeout
        self._episode_cache_seconds = episode_cache_seconds
        self._clock = clock
        self._episode_cache: dict[int, tuple[float, set[str]]] = {}
        self._seasons_cache: dict[int, tuple[float, list[SeasonInfo]]] = {}

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

    async def trending(self, media_type: str = "all") -> list[MediaResult]:
        if not self.enabled:
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        target = "movie" if media_type == "movie" else ("tv" if media_type in ("tv", "series") else "all")
        url = f"https://api.themoviedb.org/3/trending/{target}/week"
        try:
            response = await client.get(
                url, params={"api_key": self._api_key, "language": "fr-FR"}
            )
            response.raise_for_status()
            default_type = "movie" if target == "movie" else ("tv" if target == "tv" else None)
            return parse_multi(response.json(), default_type=default_type)
        except Exception as exc:  # resilience
            logger.warning("TMDB trending failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def get_details(self, media_type: str, tmdb_id: int) -> MediaResult | None:
        if not self.enabled:
            return None
        target = "movie" if media_type == "movie" else "tv"
        url = f"https://api.themoviedb.org/3/{target}/{tmdb_id}"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                url, params={"api_key": self._api_key, "language": "fr-FR"}
            )
            response.raise_for_status()
            item = response.json()
            title = item.get("title") or item.get("name") or ""
            original_title = item.get("original_title") or item.get("original_name")
            date = item.get("release_date") or item.get("first_air_date") or ""
            return MediaResult(
                tmdb_id=tmdb_id,
                media_type=target,
                title=title,
                original_title=original_title,
                year=date[:4] if date else None,
                overview=item.get("overview") or "",
                poster_path=item.get("poster_path"),
            )
        except Exception as exc:
            logger.warning("TMDB get_details(%s, %s) failed: %s", media_type, tmdb_id, exc)
            return None
        finally:
            if owns_client:
                await client.aclose()

    async def test(self) -> tuple[bool, str]:
        """Key check for the status panel: never raises, never echoes the key."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(_CONFIG_URL, params={"api_key": self._api_key})
            if response.status_code == 401:
                return False, "Clé API refusée (401)."
            response.raise_for_status()
            return True, "OK"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.ConnectError:
            return False, "Serveur injoignable (adresse introuvable ou connexion refusée)."
        except httpx.HTTPStatusError as exc:
            return False, f"Erreur HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {redact(str(exc))}."
        finally:
            if owns_client:
                await client.aclose()

    async def seasons(self, tv_id: int) -> list[SeasonInfo]:
        """Fetch structured seasons and episodes for a TV series from TMDB."""
        if not self.enabled:
            return []
        cached = self._seasons_cache.get(tv_id)
        if cached is not None and cached[0] > self._clock():
            return cached[1]
        result = await self._fetch_seasons(tv_id)
        if result:
            self._seasons_cache[tv_id] = (self._clock() + self._episode_cache_seconds, result)
        return result

    async def _fetch_seasons(self, tv_id: int) -> list[SeasonInfo]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        params = {"api_key": self._api_key, "language": "fr-FR"}
        try:
            detail = await client.get(f"{_TV_URL}/{tv_id}", params=params)
            detail.raise_for_status()
            season_data = [
                s for s in detail.json().get("seasons", [])
                if isinstance(s.get("season_number"), int) and s.get("season_number") >= 1
            ]
            season_data.sort(key=lambda s: s.get("season_number", 0))

            async def _fetch_season_episodes(number: int) -> list[EpisodeInfo]:
                try:
                    resp = await client.get(f"{_TV_URL}/{tv_id}/season/{number}", params=params)
                    resp.raise_for_status()
                    episodes: list[EpisodeInfo] = []
                    for ep in resp.json().get("episodes", []):
                        s_num = ep.get("season_number")
                        e_num = ep.get("episode_number")
                        if s_num is None or e_num is None:
                            continue
                        episodes.append(
                            EpisodeInfo(
                                season_number=int(s_num),
                                episode_number=int(e_num),
                                code=f"S{int(s_num):02d}E{int(e_num):02d}",
                                name=ep.get("name") or f"Episode {e_num}",
                                air_date=ep.get("air_date") or None,
                                overview=ep.get("overview") or "",
                            )
                        )
                    return episodes
                except Exception as exc:
                    logger.warning("TMDB season %s/%s failed: %s", tv_id, number, exc)
                    return []

            fetched_seasons = await asyncio.gather(
                *[_fetch_season_episodes(s["season_number"]) for s in season_data]
            )

            result: list[SeasonInfo] = []
            for s, eps in zip(season_data, fetched_seasons, strict=False):
                s_num = int(s["season_number"])
                result.append(
                    SeasonInfo(
                        season_number=s_num,
                        name=s.get("name") or f"Saison {s_num}",
                        overview=s.get("overview") or "",
                        poster_path=s.get("poster_path"),
                        episode_count=len(eps) or s.get("episode_count", 0),
                        episodes=eps,
                    )
                )
            return result
        except Exception as exc:  # resilience
            logger.warning("TMDB seasons failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def episodes(self, tv_id: int) -> set[str]:
        """Aired episode keys (e.g. ``S01E02``) for a series, cached with a TTL.

        Empty results (network failure or no aired episode) are never cached so a
        brand-new or transiently-failing series is re-checked next cycle.
        """
        if not self.enabled:
            return set()
        cached = self._episode_cache.get(tv_id)
        if cached is not None and cached[0] > self._clock():
            return set(cached[1])
        all_seasons = await self.seasons(tv_id)
        today = date.today().isoformat()
        keys: set[str] = set()
        for s in all_seasons:
            for ep in s.episodes:
                if not ep.air_date or ep.air_date > today:
                    continue
                keys.add(ep.code)
        if keys:
            self._episode_cache[tv_id] = (self._clock() + self._episode_cache_seconds, keys)
        return keys
