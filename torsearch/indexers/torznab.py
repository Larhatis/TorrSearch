from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET
import httpx

from torsearch.config import AuthMode, IndexerConfig
from torsearch.indexers.base import Indexer
from torsearch.models import Category, SearchResult

logger = logging.getLogger(__name__)

TORZNAB_NS = "{http://torznab.com/schemas/2015/feed}"

DEFAULT_CATEGORY_IDS: dict[Category, list[int]] = {
    Category.MOVIES: [2000],
    Category.TV: [5000],
    Category.ANIME: [5070],
    Category.OTHER: [8000],
}


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
        params: dict[str, str] = {"t": "search", "q": query}
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

    async def search(self, query: str, category: Category) -> list[SearchResult]:
        params = self._build_params(query, category)
        headers = self._build_headers()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(self._url, params=params, headers=headers)
            response.raise_for_status()
            return parse_response(response.content, self.name)
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
            response = await client.get(self._url, params=params, headers=headers)
            if response.status_code in (401, 403):
                return False, "Clé API refusée (401/403)."
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if root.tag != "caps":
                return False, "Réponse inattendue (pas un flux Torznab)."
            return True, "OK"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {exc}."
        except ET.ParseError:
            return False, "Réponse invalide (XML illisible)."
        finally:
            if owns_client:
                await client.aclose()
