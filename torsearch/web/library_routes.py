from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedMovie
from torsearch.web.authz import require_member
from torsearch.web.templating import templates

library_router = APIRouter()


@library_router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    ctx = request.app.state.ctx
    library = request.app.state.library
    series_library = request.app.state.series_library
    return templates.TemplateResponse(
        request, "library.html",
        {"movies": library.list(), "series": series_library.list(),
         "monitor_on": ctx.config.monitor.enabled,
         "owned": await ctx.jellyfin.owned(), "jellyfin_url": ctx.jellyfin.base_url},
    )


@library_router.post("/library/add", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def library_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    original_title: str = Form(""),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    library = request.app.state.library
    added = library.add(WantedMovie(
        tmdb_id=tmdb_id, title=title, original_title=original_title or None,
        year=year or None, poster_path=poster_path or None,
        status="wanted", added_at=datetime.now(UTC),
    ))
    message = "Ajoute a la bibliotheque." if added else "Deja dans la bibliotheque."
    if request.headers.get("HX-Target", "").startswith("media-action-"):
        badge = (
            f'<div id="media-action-movie-{tmdb_id}" '
            f'class="mt-1.5 flex w-full items-center justify-center gap-1 rounded '
            f'bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-xs text-emerald-400 font-medium">'
            f'<i class="ti ti-check"></i> En bibliotheque</div>'
        )
        toast = (
            f'<div id="toast" hx-swap-oob="innerHTML">'
            f'<div class="rounded bg-emerald-600 px-3 py-2 text-sm text-white shadow-lg">{message}</div></div>'
        )
        return HTMLResponse(content=f"{badge}{toast}")
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@library_router.post("/library/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def library_remove(request: Request, tmdb_id: int):
    library = request.app.state.library
    library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/library_list.html", {"movies": library.list()})
