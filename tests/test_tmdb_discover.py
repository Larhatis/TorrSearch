from __future__ import annotations

import httpx
import respx

from torsearch.config import MetadataConfig
from torsearch.metadata.tmdb import TmdbClient

API = "https://api.themoviedb.org/3"
MOVIES = {"results": [{"id": 1, "title": "Dune", "release_date": "2026-12-01", "poster_path": "/d.jpg"},
                      {"id": 2, "title": "Heat", "release_date": "1995-12-15"}]}


async def test_genres_are_cached():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        route = respx.get(f"{API}/genre/movie/list").mock(return_value=httpx.Response(
            200, json={"genres": [{"id": 28, "name": "Action"}, {"id": 18, "name": "Drame"}]}))
        assert await client.genres("movie") == [(28, "Action"), (18, "Drame")]
        await client.genres("movie")
    assert route.call_count == 1


async def test_discover_passes_genre_year_and_french_region():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        route = respx.get(f"{API}/discover/movie").mock(return_value=httpx.Response(200, json=MOVIES))
        out = await client.discover("movie", genre_id=28, year=2026)
    params = route.calls[0].request.url.params
    assert params["with_genres"] == "28" and params["primary_release_year"] == "2026"
    assert params["region"] == "FR" and params["language"] == "fr-FR"
    assert [(m.title, m.media_type, m.year) for m in out] == [("Dune", "movie", "2026"), ("Heat", "movie", "1995")]


async def test_discover_tv_uses_first_air_year():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        route = respx.get(f"{API}/discover/tv").mock(return_value=httpx.Response(
            200, json={"results": [{"id": 9, "name": "MobLand", "first_air_date": "2025-03-30"}]}))
        out = await client.discover("tv", year=2025)
    assert route.calls[0].request.url.params["first_air_date_year"] == "2025"
    assert out[0].media_type == "tv" and out[0].title == "MobLand"


async def test_upcoming_in_france_and_recommendations():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        up = respx.get(f"{API}/movie/upcoming").mock(return_value=httpx.Response(200, json=MOVIES))
        rec = respx.get(f"{API}/tv/9/recommendations").mock(return_value=httpx.Response(
            200, json={"results": [{"id": 10, "name": "Gangs of London", "first_air_date": "2020-04-23"}]}))
        assert [m.tmdb_id for m in await client.upcoming()] == [1, 2]
        assert [m.title for m in await client.recommendations("tv", 9)] == ["Gangs of London"]
    assert up.calls[0].request.url.params["region"] == "FR"
    assert rec.call_count == 1


async def test_failures_and_disabled_return_empty():
    assert await TmdbClient(MetadataConfig()).discover("movie") == []
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get(f"{API}/movie/upcoming").mock(return_value=httpx.Response(500))
        assert await client.upcoming() == []
