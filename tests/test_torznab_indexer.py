from pathlib import Path

import httpx
import respx

from torsearch.config import AuthMode, IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.models import Category

FIXTURE = (Path(__file__).parent / "fixtures" / "torznab_sample.xml").read_bytes()


def _cfg(**overrides):
    base = dict(name="tracker1", url="https://tracker1.example/api", api_key="KEY")
    base.update(overrides)
    return IndexerConfig(**base)


def test_build_params_query_auth_includes_apikey():
    ix = TorznabIndexer(_cfg(auth=AuthMode.QUERY))
    params = ix._build_params("dune", Category.MOVIES)
    assert params["t"] == "search"
    assert params["q"] == "dune"
    assert params["apikey"] == "KEY"
    assert params["cat"] == "2000"
    assert ix._build_headers() == {}


def test_build_params_bearer_auth_uses_header_not_query():
    ix = TorznabIndexer(_cfg(auth=AuthMode.BEARER))
    params = ix._build_params("dune", Category.ALL)
    assert "apikey" not in params
    assert "cat" not in params  # Category.ALL -> no cat filter
    assert ix._build_headers() == {"Authorization": "Bearer KEY"}


def test_category_override_from_config():
    ix = TorznabIndexer(_cfg(categories={"movies": [2010, 2040]}))
    params = ix._build_params("dune", Category.MOVIES)
    assert params["cat"] == "2010,2040"


async def test_search_success_returns_parsed_results():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=FIXTURE)
        )
        results = await ix.search("cool", Category.ALL)
    assert len(results) == 2
    assert results[0].source == "tracker1"


async def test_search_http_error_returns_empty():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(500)
        )
        assert await ix.search("cool", Category.ALL) == []


async def test_search_malformed_xml_returns_empty():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=b"<not-xml")
        )
        assert await ix.search("cool", Category.ALL) == []
