from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.models import MediaResult
from torsearch.web.templating import templates

discover_router = APIRouter()


def _state(request: Request) -> tuple[set[str], set[str]]:
    """Keys (``movie:<id>`` / ``tv:<id>``) already tracked or pending a request."""
    in_library: set[str] = set()
    library = request.app.state.library
    series_library = request.app.state.series_library
    if library is not None:
        in_library |= {f"movie:{m.tmdb_id}" for m in library.list()}
    if series_library is not None:
        in_library |= {f"tv:{s.tmdb_id}" for s in series_library.list()}
    store = request.app.state.requests
    requested = {f"{r.media_type}:{r.tmdb_id}" for r in store.pending()} if store else set()
    return in_library, requested


async def _get_trending(tmdb, media_type: str) -> list[MediaResult]:
    try:
        return await tmdb.trending(media_type=media_type)
    except TypeError:
        all_media = await tmdb.trending()
        if media_type == "movie":
            return [m for m in all_media if m.media_type == "movie"]
        if media_type in ("tv", "series"):
            return [m for m in all_media if m.media_type == "tv"]
        return all_media


@discover_router.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(request, "discover.html", {"has_tmdb": ctx.tmdb.enabled})


@discover_router.get("/discover/search", response_class=HTMLResponse)
async def discover_search(request: Request, q: str = "", tab: str = "all"):
    ctx = request.app.state.ctx
    media = await ctx.tmdb.search(q) if q.strip() else []
    in_library, requested = _state(request)
    movies = [m for m in media if m.media_type == "movie"]
    series = [m for m in media if m.media_type == "tv"]
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {
            "movies": movies,
            "series": series,
            "media": media,
            "query": q,
            "tab": tab,
            "owned": await ctx.jellyfin.owned(),
            "jellyfin_url": ctx.jellyfin.base_url,
            "in_library": in_library,
            "requested": requested,
        },
    )


@discover_router.get("/discover/trending", response_class=HTMLResponse)
async def discover_trending(request: Request, tab: str = "all"):
    ctx = request.app.state.ctx
    in_library, requested = _state(request)
    if tab == "movie":
        movies = await _get_trending(ctx.tmdb, "movie")
        series = []
    elif tab in ("tv", "series"):
        movies = []
        series = await _get_trending(ctx.tmdb, "tv")
    else:
        movies, series = await asyncio.gather(
            _get_trending(ctx.tmdb, "movie"),
            _get_trending(ctx.tmdb, "tv"),
        )
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {
            "movies": movies,
            "series": series,
            "media": movies + series,
            "query": "",
            "tab": tab,
            "owned": await ctx.jellyfin.owned(),
            "jellyfin_url": ctx.jellyfin.base_url,
            "in_library": in_library,
            "requested": requested,
        },
    )
