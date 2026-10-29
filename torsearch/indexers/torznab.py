from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET
import httpx

from torsearch.config import AuthMode, IndexerConfig
from torsearch.indexers.base import DEFAULT_RETRY_AFTER, Indexer, RateLimited
from torsearch.models import Category, SearchResult
from torsearch.redact import redact

logger = logging.getLogger(__name__)

TORZNAB_NS = "{http://torznab.com/schemas/2015/feed}"

DEFAULT_CATEGORY_IDS: dict[Category, list[int]] = {
    Category.MOVIES: [2000],
    Category.TV: [5000],
    Category.ANIME: [5070],
    Category.OTHER: [8000],
}

_MAX_REDIRECTS = 5


class RedirectRefused(Exception):
    """A tracker redirect we will not follow (another host, https -> http, or a loop)."""


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "").strip()
    return float(value) if value.isdigit() else DEFAULT_RETRY_AFTER


def _next_url(current: str, location: str) -> str:
    """Where to re-send a request after a redirect; raises RedirectRefused when unsafe.

    Only same-host targets are followed (http -> https allowed, never https -> http), so the
    API key never leaves the configured host nor travels unencrypted. The target's query
    string is dropped: the caller re-sends its own parameters.
    """
    cur = httpx.URL(current)
    target = cur.join(location)
    if target.host != cur.host:
        raise RedirectRefused(
            f"Redirection vers un autre site refusée ({target.host}) : mets à jour l'URL du tracker."
        )
    if cur.scheme == "https" and target.scheme != "https":
        raise RedirectRefused("Redirection vers http refusée (non chiffré).")
    path = target.raw_path.split(b"?", 1)[0].decode("ascii")
    return f"{target.scheme}://{target.netloc.decode('ascii')}{path}"


def category_from_id(cat_id: int) -> Category:
    if cat_id == 5070:
        return Category.ANIME
    if 2000 <= cat_id < 3000:
        return Category.MOVIES
    if 5000 <= cat_id < 6000:
        return Category.TV
    return Category.OTHER


def _int(value: str | None) -> int:
    if value and value.lstrip("-").isdigit():
        return int(value)
    return 0


def parse_response(xml_bytes: bytes, source: str) -> list[SearchResult]:
    root = ET.fromstring(xml_bytes)
    if root.tag == "error":
        desc = root.get("description") or "Erreur API Torznab"
        logger.warning("Indexer %s returned API error: %s", source, desc)
        return []
    results: list[SearchResult] = []
    for item in root.iter("item"):
        attrs = {a.get("name"): a.get("value") for a in item.findall(f"{TORZNAB_NS}attr")}

        title_el = item.find("title")
        title = title_el.text if title_el is not None and title_el.text else ""

        download_url = ""
        size = 0
        enclosure = item.find("enclosure")
        if enclosure is not None:
            download_url = enclosure.get("url", "")
            size = _int(enclosure.get("length"))
        if not download_url:
            link_el = item.find("link")
            if link_el is not None and link_el.text:
                download_url = link_el.text

        if size == 0:
            size_el = item.find("size")
            if size_el is not None:
                size = _int(size_el.text)
        if size == 0:
            size = _int(attrs.get("size"))

        seeders = _int(attrs.get("seeders"))
        if "leechers" in attrs:
            leechers = _int(attrs.get("leechers"))
        elif "peers" in attrs:
            leechers = max(_int(attrs.get("peers")) - seeders, 0)
        else:
            leechers = 0

        cat_value = attrs.get("category")
        category = category_from_id(int(cat_value)) if cat_value and cat_value.isdigit() else Category.OTHER

        info_url = None
        comments_el = item.find("comments")
        guid_el = item.find("guid")
        if comments_el is not None and comments_el.text:
            info_url = comments_el.text
        elif guid_el is not None and guid_el.text and guid_el.text.startswith("http"):
            info_url = guid_el.text

        publish_date = None
        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            try:
                publish_date = parsedate_to_datetime(pub_el.text)
            except (TypeError, ValueError):
                publish_date = None

        results.append(
            SearchResult(
                title=title,
                size=size,
                seeders=seeders,
                leechers=leechers,
                source=source,
                category=category,
                download_url=download_url,
                info_url=info_url,
                publish_date=publish_date,
                infohash=attrs.get("infohash"),
            )
        )
    return results


_HTML_NOT_TORZNAB = (
    "Réponse HTML reçue au lieu d'un flux Torznab XML. "
    "Vérifie l'URL (ajoute '/api/' ou '/api/torznab' à la fin)."
)


class TorznabIndexer(Indexer):
    def __init__(
        self,
        config: IndexerConfig,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        self.name = config.name
        self.enabled = config.enabled
        self._url = config.url
        self._api_key = config.api_key
        self._auth = config.auth
        self._timeout = timeout
        self._client = client
        self._category_ids = self._build_category_ids(config)

    @staticmethod
    def _build_category_ids(config: IndexerConfig) -> dict[Category, list[int]]:
        ids = dict(DEFAULT_CATEGORY_IDS)
        for key, values in config.categories.items():
            try:
                ids[Category(key)] = values
            except ValueError:
                continue
        return ids

    def _build_params(self, query: str, category: Category) -> dict[str, str]:
        params: dict[str, str] = {"t": "search", "q": query, "limit": "100"}
        if self._auth == AuthMode.QUERY:
            params["apikey"] = self._api_key
        if category != Category.ALL:
            cat_ids = self._category_ids.get(category, [])
            if cat_ids:
                params["cat"] = ",".join(str(c) for c in cat_ids)
        return params

    def _build_headers(self) -> dict[str, str]:
        if self._auth == AuthMode.BEARER:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _get(self, client: httpx.AsyncClient, params: dict[str, str],
                   headers: dict[str, str]) -> httpx.Response:
        """GET the API, following only safe same-host redirects (see ``_next_url``)."""
        url = self._url
        for _ in range(_MAX_REDIRECTS + 1):
            response = await client.get(url, params=params, headers=headers)
            if not response.is_redirect:
                return response
            url = _next_url(url, response.headers["location"])
        raise RedirectRefused("Trop de redirections.")

    async def search(self, query: str, category: Category) -> list[SearchResult]:
        params = self._build_params(query, category)
        headers = self._build_headers()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await self._get(client, params, headers)
            if response.status_code == 429:
                raise RateLimited(_retry_after(response))
            response.raise_for_status()
            return parse_response(response.content, self.name)
        except RateLimited:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.warning(
                    "Indexer %s: clé API rejetée (HTTP %d). Vérifiez la clé API dans les réglages.",
                    self.name,
                    exc.response.status_code,
                )
            else:
                logger.warning("Indexer %s failed with HTTP %d", self.name, exc.response.status_code)
            return []
        except Exception as exc:  # resilience: never raise to the orchestrator
            logger.warning("Indexer %s failed: %s", self.name, exc)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def test(self) -> tuple[bool, str]:
        params: dict[str, str] = {"t": "caps"}
        if self._auth == AuthMode.QUERY:
            params["apikey"] = self._api_key
        headers = self._build_headers()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await self._get(client, params, headers)
            if response.status_code in (401, 403):
                return False, "Clé API refusée (401/403)."
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if root.tag == "html":
                return False, _HTML_NOT_TORZNAB
            if root.tag != "caps":
                return False, "Réponse inattendue (pas un flux Torznab)."

            # Many trackers (e.g. C411, Unit3d) make `t=caps` public without validating
            # the API key. If an API key is configured, verify it with an authenticated request.
            if self._api_key:
                auth_params: dict[str, str] = {"t": "search", "limit": "1"}
                if self._auth == AuthMode.QUERY:
                    auth_params["apikey"] = self._api_key
                auth_resp = await self._get(client, auth_params, headers)
                if auth_resp.status_code in (401, 403):
                    try:
                        err_root = ET.fromstring(auth_resp.content)
                        desc = err_root.get("description")
                        if desc:
                            return False, f"Clé API refusée ({desc}) : vérifiez votre clé API dans votre profil."
                    except Exception:
                        pass
                    return False, "Clé API refusée (401/403) : vérifiez votre clé API dans votre profil."
                if auth_resp.status_code == 429:
                    return False, "Limite de requêtes atteinte (Rate limit 429)."
                auth_resp.raise_for_status()
                try:
                    auth_root = ET.fromstring(auth_resp.content)
                    if auth_root.tag == "error":
                        desc = auth_root.get("description") or "Erreur API"
                        return False, f"Clé API refusée ({desc}) : vérifiez votre clé API."
                except ET.ParseError:
                    pass

            return True, "OK"
        except RedirectRefused as exc:
            return False, str(exc)
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.ConnectError:
            return False, "Serveur injoignable (adresse introuvable ou connexion refusée)."
        except httpx.HTTPStatusError as exc:
            # The exception text embeds the request URL, passkey included: status only.
            return False, f"Erreur HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {redact(str(exc))}."
        except ET.ParseError:
            sample = response.text[:200].lstrip().lower()
            if sample.startswith(("<!doctype html", "<html")):
                return False, _HTML_NOT_TORZNAB
            return False, "Réponse invalide (XML illisible)."
        finally:
            if owns_client:
                await client.aclose()
