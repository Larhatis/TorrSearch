from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedMovie, WantedSeries
from torsearch.requests.store import RequestStatus
from torsearch.web.authz import require_admin
from torsearch.web.templating import templates

requests_router = APIRouter()


def _current_user(request: Request) -> str:
    try:
        return request.session.get("user") or "?"
    except (AssertionError, AttributeError):
        return "?"


def _toast(request: Request, ok: bool, message: str):
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})


def _request_list(request: Request, error: str | None = None, notice: str | None = None):
    store = request.app.state.requests
    return templates.TemplateResponse(
        request, "partials/request_list.html",
        {"pending": store.pending() if store else [],
         "recent": [r for r in (store.list() if store else []) if r.status != RequestStatus.PENDING][:10],
         "error": error, "notice": notice},
    )


@requests_router.post("/requests", response_class=HTMLResponse)
async def create_request(
    request: Request,
    media_type: str = Form(...),
    tmdb_id: int = Form(...),
    title: str = Form(...),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    store = request.app.state.requests
    if store is None:
        return _toast(request, False, "Demandes indisponibles.")
    store.add(_current_user(request), media_type, tmdb_id, title, year or None, poster_path or None)
    return _toast(request, True, "Demande envoyee — l'admin la validera.")


@requests_router.get("/requests", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def requests_page(request: Request):
    store = request.app.state.requests
    return templates.TemplateResponse(
        request, "requests.html",
        {"pending": store.pending() if store else [],
         "recent": [r for r in (store.list() if store else []) if r.status != RequestStatus.PENDING][:10]},
    )


def _add_to_library(request: Request, req) -> None:
    now = datetime.now(timezone.utc)
    if req.media_type == "movie":
        library = request.app.state.library
        if library is not None:
            library.add(WantedMovie(tmdb_id=req.tmdb_id, title=req.title, year=req.year,
                                    poster_path=req.poster_path, added_at=now))
    else:
        series_library = request.app.state.series_library
        if series_library is not None:
            series_library.add(WantedSeries(tmdb_id=req.tmdb_id, title=req.title, year=req.year,
                                            poster_path=req.poster_path, added_at=now))


@requests_router.post("/requests/{request_id}/approve", response_class=HTMLResponse,
                      dependencies=[Depends(require_admin)])
async def approve_request(request: Request, request_id: str):
    store = request.app.state.requests
    req = store.get(request_id) if store else None
    if req is None:
        return _request_list(request, error="Demande introuvable.")
    _add_to_library(request, req)
    store.set_status(request_id, RequestStatus.APPROVED, _current_user(request))
    return _request_list(request, notice=f"« {req.title} » approuvee et ajoutee.")


@requests_router.post("/requests/{request_id}/reject", response_class=HTMLResponse,
                      dependencies=[Depends(require_admin)])
async def reject_request(request: Request, request_id: str):
    store = request.app.state.requests
    req = store.get(request_id) if store else None
    if req is None:
        return _request_list(request, error="Demande introuvable.")
    store.set_status(request_id, RequestStatus.REJECTED, _current_user(request))
    return _request_list(request, notice=f"« {req.title} » refusee.")
