from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

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


@discover_router.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(request, "discover.html", {"has_tmdb": ctx.tmdb.enabled})


@discover_router.get("/discover/search", response_class=HTMLResponse)
async def discover_search(request: Request, q: str = ""):
    ctx = request.app.state.ctx
    media = await ctx.tmdb.search(q) if q.strip() else []
    in_library, requested = _state(request)
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {"media": media, "query": q, "owned": await ctx.jellyfin.owned(),
         "jellyfin_url": ctx.jellyfin.base_url, "in_library": in_library, "requested": requested},
    )


@discover_router.get("/discover/trending", response_class=HTMLResponse)
async def discover_trending(request: Request):
    ctx = request.app.state.ctx
    in_library, requested = _state(request)
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {"media": await ctx.tmdb.trending(), "query": "", "owned": await ctx.jellyfin.owned(),
         "jellyfin_url": ctx.jellyfin.base_url, "in_library": in_library, "requested": requested},
    )
