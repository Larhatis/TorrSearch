import httpx
import respx

from torsearch.config import JellyfinConfig
from torsearch.jellyfin.client import JellyfinClient

SAMPLE = {"Items": [
    {"Id": "aaa", "Type": "Movie", "Name": "Dune", "ProviderIds": {"Tmdb": "438631"}},
    {"Id": "bbb", "Type": "Series", "Name": "GoT", "ProviderIds": {"Tmdb": "1399"}},
    {"Id": "ccc", "Type": "Movie", "Name": "NoProvider", "ProviderIds": {}},
]}


def test_enabled_and_base_url():
    c = JellyfinClient(JellyfinConfig(url="http://jelly/", api_key="K"))
    assert c.enabled is True
    assert c.base_url == "http://jelly"
    assert JellyfinClient(JellyfinConfig()).enabled is False


async def test_owned_disabled_returns_empty():
    assert await JellyfinClient(JellyfinConfig()).owned() == {}


async def test_owned_parses_provider_ids():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Items").mock(return_value=httpx.Response(200, json=SAMPLE))
        owned = await c.owned()
    assert owned == {"movie:438631": "aaa", "tv:1399": "bbb"}


async def test_owned_http_error_returns_empty():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Items").mock(return_value=httpx.Response(500))
        assert await c.owned() == {}
