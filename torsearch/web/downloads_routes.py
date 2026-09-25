from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.redact import redact
from torsearch.web.templating import templates

downloads_router = APIRouter()

_finished_scanned: set[int] = set()


def _format_rate(bytes_per_sec: int | float) -> str:
    r = float(bytes_per_sec)
    if r >= 1024**2:
        return f"{r / (1024**2):.1f} Mo/s"
    if r >= 1024:
        return f"{r / 1024:.0f} Ko/s"
    return f"{int(r)} o/s"


async def _render_list(request: Request, error: str | None = None):
    ctx: AppContext = request.app.state.ctx
    torrents = []
    if error is None:
        try:
            torrents = await ctx.transmission.list_torrents()
        except Exception as exc:
            error = f"Transmission injoignable : {redact(str(exc))}"

    total_down = sum(t.down_rate for t in torrents)
    total_up = sum(t.up_rate for t in torrents)
    active_count = sum(
        1 for t in torrents if t.down_rate > 0 or t.up_rate > 0 or t.status in ("downloading", "seeding")
    )

    # Auto-trigger Jellyfin scan when a torrent completes
    if hasattr(ctx, "jellyfin") and ctx.jellyfin and ctx.jellyfin.enabled:
        for t in torrents:
            if (t.percent >= 100.0 or "seed" in t.status.lower()) and t.id not in _finished_scanned:
                _finished_scanned.add(t.id)
                try:
                    asyncio.create_task(ctx.jellyfin.refresh())
                except Exception:
                    pass

    return templates.TemplateResponse(
        request,
        "partials/downloads_list.html",
        {
            "torrents": torrents,
            "error": error,
            "total_down_formatted": _format_rate(total_down),
            "total_up_formatted": _format_rate(total_up),
            "active_count": active_count,
        },
    )


@downloads_router.get("/downloads", response_class=HTMLResponse)
@downloads_router.get("/activity", response_class=HTMLResponse)
async def downloads_page(request: Request):
    return templates.TemplateResponse(request, "downloads.html", {})


@downloads_router.get("/downloads/list", response_class=HTMLResponse)
@downloads_router.get("/activity/list", response_class=HTMLResponse)
async def downloads_list(request: Request):
    return await _render_list(request)


@downloads_router.post("/downloads/scan-jellyfin", response_class=HTMLResponse)
@downloads_router.post("/activity/scan-jellyfin", response_class=HTMLResponse)
async def scan_jellyfin(request: Request):
    ctx: AppContext = request.app.state.ctx
    ok = False
    if hasattr(ctx, "jellyfin") and ctx.jellyfin and ctx.jellyfin.enabled:
        try:
            await ctx.jellyfin.refresh()
            ok = True
        except Exception:
            pass
    msg = "Scan Jellyfin lance avec succes." if ok else "Jellyfin non disponible ou desactive."
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": msg})


@downloads_router.post("/downloads/{torrent_id}/pause", response_class=HTMLResponse)
@downloads_router.post("/activity/{torrent_id}/pause", response_class=HTMLResponse)
async def pause(request: Request, torrent_id: int):
    try:
        await request.app.state.ctx.transmission.pause(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}")
    return await _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/resume", response_class=HTMLResponse)
@downloads_router.post("/activity/{torrent_id}/resume", response_class=HTMLResponse)
async def resume(request: Request, torrent_id: int):
    try:
        await request.app.state.ctx.transmission.resume(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}")
    return await _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/delete", response_class=HTMLResponse)
@downloads_router.post("/activity/{torrent_id}/delete", response_class=HTMLResponse)
async def delete(request: Request, torrent_id: int, delete_data: bool = False):
    try:
        await request.app.state.ctx.transmission.remove(torrent_id, delete_data=delete_data)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}")
    return await _render_list(request)

