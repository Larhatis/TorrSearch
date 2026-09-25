from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import MediaResult, WantedMovie, WantedSeries
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


async def _get_details(tmdb, media_type: str, tmdb_id: int) -> MediaResult | None:
    if hasattr(tmdb, "get_details"):
        res = await tmdb.get_details(media_type, tmdb_id)
        if res is not None:
            return res
    if hasattr(tmdb, "search"):
        try:
            results = await tmdb.search("")
            for m in results:
                if m.tmdb_id == tmdb_id:
                    return m
        except Exception:
            pass
    return None


@discover_router.get("/discover/{media_type}/{tmdb_id}/modal", response_class=HTMLResponse)
async def discover_modal(request: Request, media_type: str, tmdb_id: int):
    ctx = request.app.state.ctx
    m = await _get_details(ctx.tmdb, media_type, tmdb_id)
    if m is None:
        m = MediaResult(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=f"{media_type.capitalize()} #{tmdb_id}",
        )
    in_library, _ = _state(request)
    key = f"{media_type}:{tmdb_id}"
    owned = await ctx.jellyfin.owned()
    return templates.TemplateResponse(
        request,
        "partials/media_detail_modal.html",
        {
            "m": m,
            "in_library": key in in_library,
            "owned_jf": owned.get(key),
            "jellyfin_url": ctx.jellyfin.base_url,
        },
    )


@discover_router.post("/discover/library/add", response_class=HTMLResponse)
async def discover_library_add(
    request: Request,
    media_type: str = Form(...),
    tmdb_id: int = Form(...),
    title: str = Form(...),
    original_title: str = Form(""),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    now = datetime.now(UTC)
    if media_type == "movie":
        library = request.app.state.library
        if library is not None:
            library.add(
                WantedMovie(
                    tmdb_id=tmdb_id,
                    title=title,
                    original_title=original_title or None,
                    year=year or None,
                    poster_path=poster_path or None,
                    status="wanted",
                    added_at=now,
                )
            )
        message = "Film ajoute a la bibliotheque."
    else:
        series_library = request.app.state.series_library
        if series_library is not None:
            series_library.add(
                WantedSeries(
                    tmdb_id=tmdb_id,
                    title=title,
                    original_title=original_title or None,
                    year=year or None,
                    poster_path=poster_path or None,
                    added_at=now,
                )
            )
        message = "Serie suivie."

    badge = (
        f'<div id="media-action-{media_type}-{tmdb_id}" '
        f'class="mt-1.5 flex w-full items-center justify-center gap-1 rounded '
        f'bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-xs text-emerald-400 font-medium">'
        f'<i class="ti ti-check"></i> En bibliotheque</div>'
    )
    toast = (
        f'<div id="toast" hx-swap-oob="innerHTML">'
        f'<div class="rounded bg-emerald-600 px-3 py-2 text-sm text-white shadow-lg">{message}</div></div>'
    )
    return HTMLResponse(content=f"{badge}{toast}")

