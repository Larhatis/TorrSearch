from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedSeries
from torsearch.web.authz import require_member
from torsearch.web.templating import templates

series_router = APIRouter()


@series_router.post("/series/add", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def series_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    original_title: str = Form(""),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    series_library = request.app.state.series_library
    added = series_library.add(WantedSeries(
        tmdb_id=tmdb_id, title=title, original_title=original_title or None,
        year=year or None, poster_path=poster_path or None,
        added_at=datetime.now(UTC),
    ))
    message = "Serie suivie." if added else "Serie deja suivie."
    if request.headers.get("HX-Target", "").startswith("media-action-"):
        badge = (
            f'<div id="media-action-tv-{tmdb_id}" '
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


@series_router.post("/series/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def series_remove(request: Request, tmdb_id: int):
    series_library = request.app.state.series_library
    series_library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/series_list.html", {"series": series_library.list()})
