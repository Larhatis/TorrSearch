from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.web.templating import templates

downloads_router = APIRouter()


def _render_list(request: Request, error: str | None = None):
    ctx: AppContext = request.app.state.ctx
    torrents = []
    if error is None:
        try:
            torrents = ctx.transmission.list_torrents()
        except Exception as exc:
            error = f"Transmission injoignable : {exc}"
    return templates.TemplateResponse(
        request, "partials/downloads_list.html", {"torrents": torrents, "error": error}
    )


@downloads_router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request):
    return templates.TemplateResponse(request, "downloads.html", {})


@downloads_router.get("/downloads/list", response_class=HTMLResponse)
async def downloads_list(request: Request):
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/pause", response_class=HTMLResponse)
async def pause(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.pause(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/resume", response_class=HTMLResponse)
async def resume(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.resume(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/delete", response_class=HTMLResponse)
async def delete(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.remove(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)
