from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.web.templating import templates

discover_router = APIRouter()


@discover_router.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(request, "discover.html", {"has_tmdb": ctx.tmdb.enabled})


@discover_router.get("/discover/search", response_class=HTMLResponse)
async def discover_search(request: Request, q: str = ""):
    ctx = request.app.state.ctx
    media = await ctx.tmdb.search(q) if q.strip() else []
    return templates.TemplateResponse(
        request, "partials/media_results.html", {"media": media, "query": q}
    )
