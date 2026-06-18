from pathlib import Path

from torsearch.indexers.torznab import category_from_id, parse_response
from torsearch.models import Category

FIXTURE = (Path(__file__).parent / "fixtures" / "torznab_sample.xml").read_bytes()


def test_parse_returns_two_results():
    results = parse_response(FIXTURE, "torr9")
    assert len(results) == 2


def test_parse_first_item_fields():
    r = parse_response(FIXTURE, "torr9")[0]
    assert r.title == "Cool.Movie.2024.1080p.BluRay.x264"
    assert r.size == 2147483648
    assert r.seeders == 120
    assert r.leechers == 15  # peers(135) - seeders(120)
    assert r.source == "torr9"
    assert r.category == Category.MOVIES
    assert r.download_url == "magnet:?xt=urn:btih:AAAA1111"
    assert r.is_magnet is True
    assert r.infohash == "AAAA1111"
    assert r.info_url == "https://torr9/details/111"


def test_parse_second_item_uses_enclosure_size_and_direct_leechers():
    r = parse_response(FIXTURE, "torr9")[1]
    assert r.size == 734003200
    assert r.seeders == 40
    assert r.leechers == 8
    assert r.category == Category.TV
    assert r.download_url == "https://torr9/download/222.torrent"
    assert r.is_magnet is False
    assert r.info_url == "https://torr9/details/222"


def test_parse_empty_feed_returns_empty_list():
    empty = b'<?xml version="1.0"?><rss><channel></channel></rss>'
    assert parse_response(empty, "torr9") == []


def test_category_from_id_mapping():
    assert category_from_id(2040) == Category.MOVIES
    assert category_from_id(5070) == Category.ANIME
    assert category_from_id(5040) == Category.TV
    assert category_from_id(8000) == Category.OTHER
