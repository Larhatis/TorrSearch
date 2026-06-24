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


async def test_refresh_posts_to_library_refresh():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        route = respx.post("http://jelly/Library/Refresh").mock(
            return_value=httpx.Response(204)
        )
        assert await c.refresh() is True
        assert route.called
        assert route.calls.last.request.url.params["api_key"] == "K"


async def test_refresh_disabled_is_noop():
    assert await JellyfinClient(JellyfinConfig()).refresh() is False


async def test_refresh_error_returns_false():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.post("http://jelly/Library/Refresh").mock(return_value=httpx.Response(500))
        assert await c.refresh() is False


EPISODES = {"Items": [
    {"Id": "e1", "ParentIndexNumber": 1, "IndexNumber": 1},
    {"Id": "e2", "ParentIndexNumber": 1, "IndexNumber": 2},
    {"Id": "e3", "ParentIndexNumber": 2, "IndexNumber": 10},
    {"Id": "bad", "ParentIndexNumber": 1},  # missing episode number -> ignored
]}


async def test_episodes_parses_season_episode_keys():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Shows/bbb/Episodes").mock(
            return_value=httpx.Response(200, json=EPISODES)
        )
        keys = await c.episodes("bbb")
    assert keys == {"S01E01", "S01E02", "S02E10"}


async def test_episodes_disabled_or_no_id_returns_empty():
    assert await JellyfinClient(JellyfinConfig()).episodes("bbb") == set()
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    assert await c.episodes("") == set()


async def test_episodes_error_returns_empty():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Shows/bbb/Episodes").mock(return_value=httpx.Response(500))
        assert await c.episodes("bbb") == set()
