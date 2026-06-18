from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET

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
