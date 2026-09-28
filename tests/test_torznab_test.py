import httpx
import respx

from torsearch.config import IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer

CAPS_OK = b'<?xml version="1.0"?><caps><server/></caps>'


def _cfg(**o):
    base = dict(name="t", url="https://t/api", api_key="KEY")
    base.update(o)
    return IndexerConfig(**base)


async def test_returns_ok_on_valid_caps():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(200, content=CAPS_OK))
        ok, msg = await ix.test()
    assert ok is True
    assert msg == "OK"


async def test_reports_rejected_key_on_401():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(401))
        ok, msg = await ix.test()
    assert ok is False
    assert "refus" in msg.lower()


async def test_reports_unexpected_response_on_non_caps_xml():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(200, content=b"<rss><channel/></rss>"))
        ok, msg = await ix.test()
    assert ok is False
    assert "pas un flux Torznab" in msg


async def test_reports_html_response_on_doctype_html():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(
            return_value=httpx.Response(200, content=b"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>Tr4ker</body></html>")
        )
        ok, msg = await ix.test()
    assert ok is False
    assert "HTML" in msg
    assert "/api/" in msg


async def test_reports_html_response_on_html_root_tag():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(
            return_value=httpx.Response(200, content=b"<html><body>Tr4ker</body></html>")
        )
        ok, msg = await ix.test()
    assert ok is False
    assert "HTML" in msg
    assert "/api/" in msg


async def test_sends_caps_query_with_apikey():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        route = respx.get("https://t/api").mock(return_value=httpx.Response(200, content=CAPS_OK))
        await ix.test()
    url = str(route.calls.last.request.url)
    assert "t=caps" in url
    assert "apikey=KEY" in url


async def test_reports_unreachable_server_plainly():
    ix = TorznabIndexer(IndexerConfig(name="t", url="https://t.example/api", api_key="k"))
    with respx.mock:
        respx.get("https://t.example/api").mock(side_effect=httpx.ConnectError("[Errno 8] nodename nor servname"))
        ok, msg = await ix.test()
    assert ok is False and "injoignable" in msg.lower() and "Errno" not in msg
