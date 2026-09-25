from pathlib import Path

import httpx
import respx

from torsearch.config import IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.models import Category

CAPS = b'<?xml version="1.0"?><caps/>'
SAMPLE = (Path(__file__).parent / "fixtures" / "torznab_sample.xml").read_bytes()


def _indexer(url="https://t.example/api"):
    return TorznabIndexer(IndexerConfig(name="t", url=url, api_key="K"))


async def test_follows_a_same_site_redirect_and_resends_its_params():
    # Real case: /api answers 301 -> /api/ (a trailing slash), without the query string.
    with respx.mock:
        respx.get("https://t.example/api").mock(
            return_value=httpx.Response(301, headers={"Location": "https://t.example/api/"}))
        final = respx.get("https://t.example/api/").mock(return_value=httpx.Response(200, content=CAPS))
        assert await _indexer().test() == (True, "OK")
    params = final.calls.last.request.url.params
    assert params["t"] == "caps" and params["apikey"] == "K"


async def test_follows_a_relative_redirect():
    with respx.mock:
        respx.get("https://t.example/api").mock(return_value=httpx.Response(308, headers={"Location": "/api/"}))
        respx.get("https://t.example/api/").mock(return_value=httpx.Response(200, content=CAPS))
        assert await _indexer().test() == (True, "OK")


async def test_upgrades_http_to_https_on_the_same_host():
    with respx.mock:
        respx.get("http://t.example/api").mock(
            return_value=httpx.Response(301, headers={"Location": "https://t.example/api"}))
        respx.get("https://t.example/api").mock(return_value=httpx.Response(200, content=CAPS))
        assert await _indexer("http://t.example/api").test() == (True, "OK")


async def test_refuses_a_redirect_to_another_site():
    with respx.mock:
        respx.get("https://t.example/api").mock(
            return_value=httpx.Response(302, headers={"Location": "https://evil.example/steal"}))
        evil = respx.get("https://evil.example/steal").mock(return_value=httpx.Response(200, content=CAPS))
        ok, message = await _indexer().test()
    assert ok is False
    assert "evil.example" in message and "refusée" in message
    assert not evil.called  # the key never leaves the configured host


async def test_refuses_a_downgrade_to_http():
    with respx.mock:
        respx.get("https://t.example/api").mock(
            return_value=httpx.Response(301, headers={"Location": "http://t.example/api"}))
        plain = respx.get("http://t.example/api").mock(return_value=httpx.Response(200, content=CAPS))
        ok, message = await _indexer().test()
    assert ok is False and "http" in message and "refusée" in message
    assert not plain.called  # the key is never sent unencrypted


async def test_stops_a_redirect_loop():
    with respx.mock:
        respx.get("https://t.example/api").mock(
            return_value=httpx.Response(301, headers={"Location": "https://t.example/api"}))
        assert await _indexer().test() == (False, "Trop de redirections.")


async def test_search_follows_a_same_site_redirect():
    with respx.mock:
        respx.get("https://t.example/api").mock(
            return_value=httpx.Response(301, headers={"Location": "https://t.example/api/"}))
        final = respx.get("https://t.example/api/").mock(return_value=httpx.Response(200, content=SAMPLE))
        results = await _indexer().search("dune", Category.MOVIES)
    assert results  # parsed from the redirected response
    params = final.calls.last.request.url.params
    assert params["t"] == "search" and params["q"] == "dune" and params["apikey"] == "K"
