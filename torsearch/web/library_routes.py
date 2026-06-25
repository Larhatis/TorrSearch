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
    year: str = Form(""),
    poster_path: str = Form(""),
):
    library = request.app.state.library
    added = library.add(WantedMovie(
        tmdb_id=tmdb_id, title=title, year=year or None, poster_path=poster_path or None,
        status="wanted", added_at=datetime.now(UTC),
    ))
    message = "Ajoute a la bibliotheque." if added else "Deja dans la bibliotheque."
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@library_router.post("/library/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def library_remove(request: Request, tmdb_id: int):
    library = request.app.state.library
    library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/library_list.html", {"movies": library.list()})
