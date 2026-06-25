from __future__ import annotations

from datetime import datetime, timezone

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
    year: str = Form(""),
    poster_path: str = Form(""),
):
    series_library = request.app.state.series_library
    added = series_library.add(WantedSeries(
        tmdb_id=tmdb_id, title=title, year=year or None, poster_path=poster_path or None,
        added_at=datetime.now(timezone.utc),
    ))
    message = "Serie suivie." if added else "Serie deja suivie."
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@series_router.post("/series/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def series_remove(request: Request, tmdb_id: int):
    series_library = request.app.state.series_library
    series_library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/series_list.html", {"series": series_library.list()})
