import httpx
import respx

from torsearch.config import MetadataConfig
from torsearch.metadata.tmdb import TmdbClient, parse_multi

SAMPLE = {
    "results": [
        {"id": 693134, "media_type": "movie", "title": "Dune : Deuxieme partie",
         "original_title": "Dune: Part Two",
         "release_date": "2024-02-27", "overview": "Paul Atreides...", "poster_path": "/a.jpg"},
        {"id": 1399, "media_type": "tv", "name": "Le Trone de fer",
         "original_name": "Game of Thrones",
         "first_air_date": "2011-04-17", "overview": "Neuf familles...", "poster_path": None},
        {"id": 500, "media_type": "person", "name": "Un Acteur"},
    ]
}


def test_parse_multi_maps_and_filters():
    out = parse_multi(SAMPLE)
    assert len(out) == 2
    movie = out[0]
    assert movie.media_type == "movie"
    assert movie.title == "Dune : Deuxieme partie"
    assert movie.original_title == "Dune: Part Two"
    assert movie.year == "2024"
    assert movie.poster_url == "https://image.tmdb.org/t/p/w342/a.jpg"
    tv = out[1]
    assert tv.media_type == "tv"
    assert tv.title == "Le Trone de fer"
    assert tv.original_title == "Game of Thrones"
    assert tv.year == "2011"
    assert tv.poster_url is None


def test_enabled_reflects_key():
    assert TmdbClient(MetadataConfig(tmdb_api_key="K")).enabled is True
    assert TmdbClient(MetadataConfig()).enabled is False


async def test_search_disabled_returns_empty_without_request():
    assert await TmdbClient(MetadataConfig()).search("dune") == []


async def test_search_success_parses_results():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(200, json=SAMPLE)
        )
        out = await client.search("dune")
    assert [m.title for m in out] == ["Dune : Deuxieme partie", "Le Trone de fer"]


async def test_search_http_error_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(500)
        )
        assert await client.search("dune") == []


async def test_search_malformed_json_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        assert await client.search("dune") == []


async def test_trending_returns_media():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/trending/all/week").mock(
            return_value=httpx.Response(200, json=SAMPLE)
        )
        out = await client.trending()
    assert [m.title for m in out] == ["Dune : Deuxieme partie", "Le Trone de fer"]


async def test_trending_specific_media_type():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    movies_sample = {
        "results": [
            {"id": 693134, "title": "Dune", "release_date": "2024-02-27", "overview": "Paul..."}
        ]
    }
    tv_sample = {
        "results": [
            {"id": 1399, "name": "Game of Thrones", "first_air_date": "2011-04-17", "overview": "Neuf..."}
        ]
    }
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/trending/movie/week").mock(
            return_value=httpx.Response(200, json=movies_sample)
        )
        respx.get("https://api.themoviedb.org/3/trending/tv/week").mock(
            return_value=httpx.Response(200, json=tv_sample)
        )
        movies = await client.trending("movie")
        assert len(movies) == 1
        assert movies[0].media_type == "movie"
        assert movies[0].title == "Dune"

        tv = await client.trending("tv")
        assert len(tv) == 1
        assert tv[0].media_type == "tv"
        assert tv[0].title == "Game of Thrones"


async def test_trending_disabled_returns_empty():
    assert await TmdbClient(MetadataConfig()).trending() == []


async def test_trending_error_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/trending/all/week").mock(
            return_value=httpx.Response(500)
        )
        assert await client.trending() == []


TV_DETAIL = {"seasons": [
    {"season_number": 0, "episode_count": 2},  # specials -> skipped
    {"season_number": 1, "episode_count": 3},
    {"season_number": 2, "episode_count": 2},
]}
SEASON_1 = {"episodes": [
    {"season_number": 1, "episode_number": 1, "air_date": "2020-01-01"},
    {"season_number": 1, "episode_number": 2, "air_date": "2020-01-08"},
    {"season_number": 1, "episode_number": 3, "air_date": "2099-01-01"},  # unaired
]}
SEASON_2 = {"episodes": [
    {"season_number": 2, "episode_number": 1, "air_date": "2021-01-01"},
    {"season_number": 2, "episode_number": 2, "air_date": ""},  # no air date -> skipped
]}


async def test_seasons_returns_structured_info():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/tv/42").mock(
            return_value=httpx.Response(200, json=TV_DETAIL))
        respx.get("https://api.themoviedb.org/3/tv/42/season/1").mock(
            return_value=httpx.Response(200, json=SEASON_1))
        respx.get("https://api.themoviedb.org/3/tv/42/season/2").mock(
            return_value=httpx.Response(200, json=SEASON_2))
        seasons = await client.seasons(42)
    assert len(seasons) == 2
    s1, s2 = seasons
    assert s1.season_number == 1
    assert s1.season_tag == "S01"
    assert len(s1.episodes) == 3
    assert [ep.code for ep in s1.episodes] == ["S01E01", "S01E02", "S01E03"]
    assert s2.season_number == 2
    assert s2.season_tag == "S02"
    assert len(s2.episodes) == 2


async def test_seasons_disabled_returns_empty():
    assert await TmdbClient(MetadataConfig()).seasons(42) == []


async def test_seasons_cached_within_ttl():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"), episode_cache_seconds=600, clock=lambda: 1000.0)
    with respx.mock:
        detail = _mock_full_series()
        s1 = await client.seasons(42)
        s2 = await client.seasons(42)
    assert len(s1) == len(s2) == 2
    assert detail.call_count == 1


async def test_episodes_aggregates_aired_only():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/tv/42").mock(
            return_value=httpx.Response(200, json=TV_DETAIL))
        respx.get("https://api.themoviedb.org/3/tv/42/season/1").mock(
            return_value=httpx.Response(200, json=SEASON_1))
        respx.get("https://api.themoviedb.org/3/tv/42/season/2").mock(
            return_value=httpx.Response(200, json=SEASON_2))
        keys = await client.episodes(42)
    assert keys == {"S01E01", "S01E02", "S02E01"}


async def test_episodes_disabled_returns_empty():
    assert await TmdbClient(MetadataConfig()).episodes(42) == set()


async def test_episodes_error_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/tv/42").mock(return_value=httpx.Response(500))
        assert await client.episodes(42) == set()


def _mock_full_series():
    detail = respx.get("https://api.themoviedb.org/3/tv/42").mock(
        return_value=httpx.Response(200, json=TV_DETAIL))
    respx.get("https://api.themoviedb.org/3/tv/42/season/1").mock(
        return_value=httpx.Response(200, json=SEASON_1))
    respx.get("https://api.themoviedb.org/3/tv/42/season/2").mock(
        return_value=httpx.Response(200, json=SEASON_2))
    return detail


async def test_episodes_cached_within_ttl():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"), episode_cache_seconds=600, clock=lambda: 1000.0)
    with respx.mock:
        detail = _mock_full_series()
        first = await client.episodes(42)
        second = await client.episodes(42)  # served from cache, no HTTP
    assert first == second == {"S01E01", "S01E02", "S02E01"}
    assert detail.call_count == 1


async def test_episodes_cache_expires():
    now = [1000.0]
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"), episode_cache_seconds=60, clock=lambda: now[0])
    with respx.mock:
        detail = _mock_full_series()
        await client.episodes(42)
        now[0] += 120  # advance past TTL
        await client.episodes(42)
    assert detail.call_count == 2


async def test_episodes_empty_result_not_cached():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"), clock=lambda: 1000.0)
    with respx.mock:
        detail = respx.get("https://api.themoviedb.org/3/tv/42").mock(
            return_value=httpx.Response(200, json={"seasons": []}))
        assert await client.episodes(42) == set()
        assert await client.episodes(42) == set()
    assert detail.call_count == 2  # empty results are re-fetched, never cached


async def test_test_ok_with_valid_key():
    from torsearch.config import MetadataConfig
    from torsearch.metadata.tmdb import TmdbClient

    with respx.mock:
        respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(200, json={}))
        assert await TmdbClient(MetadataConfig(tmdb_api_key="k")).test() == (True, "OK")


async def test_test_rejected_key_never_echoed():
    from torsearch.config import MetadataConfig
    from torsearch.metadata.tmdb import TmdbClient

    with respx.mock:
        respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(401))
        ok, message = await TmdbClient(MetadataConfig(tmdb_api_key="TMDB-SECRET")).test()
    assert ok is False and "refusée" in message and "TMDB-SECRET" not in message


async def test_test_reports_unreachable_server_plainly():
    from torsearch.config import MetadataConfig
    from torsearch.metadata.tmdb import TmdbClient

    with respx.mock:
        respx.get("https://api.themoviedb.org/3/configuration").mock(side_effect=httpx.ConnectError("[Errno 8] dns"))
        ok, message = await TmdbClient(MetadataConfig(tmdb_api_key="k")).test()
    assert ok is False and "injoignable" in message.lower() and "Errno" not in message
