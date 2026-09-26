from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.redact import redact
from torsearch.transmission.client import TorrentInfo
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


def _filter_torrents(
    torrents: list[TorrentInfo], filter_status: str
) -> tuple[list[TorrentInfo], dict[str, int], str]:
    counts = {
        "all": len(torrents),
        "downloading": sum(1 for t in torrents if t.percent < 100.0 and t.status != "stopped"),
        "completed": sum(1 for t in torrents if t.percent >= 100.0 or "seed" in t.status.lower()),
        "active": sum(1 for t in torrents if t.down_rate > 0 or t.up_rate > 0),
        "paused": sum(1 for t in torrents if t.status == "stopped" or t.status_label == "En pause"),
    }
    if filter_status == "downloading":
        filtered = [t for t in torrents if t.percent < 100.0 and t.status != "stopped"]
    elif filter_status == "completed":
        filtered = [t for t in torrents if t.percent >= 100.0 or "seed" in t.status.lower()]
    elif filter_status == "active":
        filtered = [t for t in torrents if t.down_rate > 0 or t.up_rate > 0]
    elif filter_status == "paused":
        filtered = [t for t in torrents if t.status == "stopped" or t.status_label == "En pause"]
    else:
        filter_status = "all"
        filtered = torrents
    return filtered, counts, filter_status


async def _render_list(request: Request, error: str | None = None, filter_status: str = "all"):
    ctx: AppContext = request.app.state.ctx
    torrents: list[TorrentInfo] = []
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

    filtered_torrents, counts, current_filter = _filter_torrents(torrents, filter_status)

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
            "torrents": filtered_torrents,
            "all_torrents_count": len(torrents),
            "counts": counts,
            "current_filter": current_filter,
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
async def downloads_list(request: Request, filter: str = "all"):
    return await _render_list(request, filter_status=filter)


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
async def pause(request: Request, torrent_id: int, filter: str = "all"):
    try:
        await request.app.state.ctx.transmission.pause(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}", filter_status=filter)
    return await _render_list(request, filter_status=filter)


@downloads_router.post("/downloads/{torrent_id}/resume", response_class=HTMLResponse)
@downloads_router.post("/activity/{torrent_id}/resume", response_class=HTMLResponse)
async def resume(request: Request, torrent_id: int, filter: str = "all"):
    try:
        await request.app.state.ctx.transmission.resume(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}", filter_status=filter)
    return await _render_list(request, filter_status=filter)


@downloads_router.post("/downloads/{torrent_id}/delete", response_class=HTMLResponse)
@downloads_router.post("/activity/{torrent_id}/delete", response_class=HTMLResponse)
async def delete(request: Request, torrent_id: int, delete_data: bool = False, filter: str = "all"):
    try:
        await request.app.state.ctx.transmission.remove(torrent_id, delete_data=delete_data)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {redact(str(exc))}", filter_status=filter)
    return await _render_list(request, filter_status=filter)

