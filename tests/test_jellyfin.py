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
        assert route.calls.last.request.headers["Authorization"] == 'MediaBrowser Token="K"'


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


async def test_test_reports_server_name_and_version():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(
            return_value=httpx.Response(200, json={"ServerName": "omvnas", "Version": "10.10.3"}))
        assert await client.test() == (True, "omvnas · Jellyfin 10.10.3")


async def test_test_rejected_key():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="BAD"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(return_value=httpx.Response(401))
        ok, message = await client.test()
    assert ok is False and "refusée" in message


async def test_test_error_never_echoes_the_key():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="JF-SECRET"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(return_value=httpx.Response(500))
        ok, message = await client.test()
    assert ok is False
    assert "500" in message and "JF-SECRET" not in message


async def test_test_reports_unreachable_server_plainly():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(side_effect=httpx.ConnectError("[Errno 111] Connection refused"))
        ok, message = await client.test()
    assert ok is False and "injoignable" in message.lower() and "Errno" not in message


# Jellyfin 12 dropped the legacy ``api_key`` query parameter: the key must travel in the
# ``Authorization: MediaBrowser Token="..."`` header, and never in the URL.
async def test_every_call_authenticates_with_the_mediabrowser_header():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        routes = [
            respx.get("http://jelly/System/Info").mock(return_value=httpx.Response(200, json={})),
            respx.get("http://jelly/Items").mock(return_value=httpx.Response(200, json={"Items": []})),
            respx.post("http://jelly/Library/Refresh").mock(return_value=httpx.Response(204)),
            respx.get("http://jelly/Shows/abc/Episodes").mock(return_value=httpx.Response(200, json={"Items": []})),
        ]
        await client.test()
        await client.owned()
        await client.refresh()
        await client.episodes("abc")
    for route in routes:
        request = route.calls.last.request
        assert request.headers["Authorization"] == 'MediaBrowser Token="K"'
        assert "api_key" not in request.url.params


async def test_find_matching_exact_and_release_queries():
    sample = {"Items": [
        {"Id": "m1", "Type": "Movie", "Name": "Inception", "ProductionYear": 2010, "ProviderIds": {"Tmdb": "27205"}},
        {"Id": "s1", "Type": "Series", "Name": "Lost", "ProductionYear": 2004, "ProviderIds": {"Tmdb": "4607"}},
        {"Id": "m2", "Type": "Movie", "Name": "Avatar", "ProductionYear": 2009, "ProviderIds": {"Tmdb": "19995"}},
    ]}
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Items").mock(return_value=httpx.Response(200, json=sample))

        # Exact title
        m1 = await c.find_matching("Inception")
        assert m1 is not None
        assert m1.id == "m1"
        assert m1.name == "Inception"
        assert m1.media_type == "movie"
        assert m1.year == 2010

        # Release string with year, quality, language
        m2 = await c.find_matching("Inception.2010.FRENCH.1080p.BluRay")
        assert m2 is not None
        assert m2.id == "m1"

        # Series with season/ep
        s1 = await c.find_matching("Lost S01E03 720p")
        assert s1 is not None
        assert s1.id == "s1"
        assert s1.name == "Lost"
        assert s1.media_type == "tv"

        # False positive rejection
        assert await c.find_matching("Avatar The Way of Water") is None
        assert await c.find_matching("Lost in Space") is None
        assert await c.find_matching("Gladiator") is None
