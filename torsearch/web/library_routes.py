from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from torsearch.models import WantedMovie
from torsearch.web.authz import require_member
from torsearch.web.templating import templates

library_router = APIRouter()


@library_router.get("/library")
async def library_page(request: Request):
    if request.headers.get("HX-Request"):
        return HTMLResponse(content="", headers={"HX-Redirect": "/surveillance"})
    return RedirectResponse(url="/surveillance", status_code=307)


@library_router.post("/library/add", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def library_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    original_title: str = Form(""),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    ctx = request.app.state.ctx
    library = request.app.state.library
    added = library.add(WantedMovie(
        tmdb_id=tmdb_id, title=title, original_title=original_title or None,
        year=year or None, poster_path=poster_path or None,
        status="wanted", added_at=datetime.now(UTC),
    ))
    if hasattr(ctx, "update_settings") and hasattr(ctx, "config") and not ctx.config.monitor.enabled:
        from torsearch.settings.mutations import set_monitor
        ctx.update_settings(set_monitor(ctx.config, ctx.config.monitor.model_copy(update={"enabled": True})))
    runner = getattr(request.app.state, "monitor", None)
    if runner is not None:
        runner.wake()

    if added:
        message = f"« {title} » sera automatiquement telecharge des sa sortie en torrent."
    else:
        message = f"« {title} » est deja sous surveillance."
    target = request.headers.get("HX-Target", "")
    badge = (
        f'<div id="{target or f"media-action-movie-{tmdb_id}"}" '
        f'class="mt-1.5 inline-flex w-full items-center justify-center gap-1 rounded '
        f'bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-xs text-emerald-400 font-medium">'
        f'<i class="ti ti-check"></i> En surveillance</div>'
    )
    toast = (
        f'<div id="toast" hx-swap-oob="innerHTML">'
        f'<div class="rounded bg-emerald-600 px-3 py-2 text-sm text-white shadow-lg">{message}</div></div>'
    )
    if target:
        return HTMLResponse(content=f"{badge}{toast}")
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@library_router.post("/library/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def library_remove(request: Request, tmdb_id: int):
    library = request.app.state.library
    library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/library_list.html", {"movies": library.list()})
