from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.library.cleanup import error_groups, find_duplicates
from torsearch.redact import redact
from torsearch.web.templating import templates

cleanup_router = APIRouter()


async def _torrents(request: Request):
    return await request.app.state.ctx.transmission.list_torrents()


async def _render(request: Request, page: bool = False, notice: str | None = None, error: str | None = None):
    groups, errors = [], []
    try:
        torrents = await _torrents(request)
        groups, errors = find_duplicates(torrents), error_groups(torrents)
    except Exception as exc:
        error = f"Transmission injoignable : {redact(str(exc))}"
    data = {"groups": groups, "errors": errors, "notice": notice, "error": error}
    return templates.TemplateResponse(request, "cleanup.html" if page else "partials/cleanup_body.html", data)


@cleanup_router.get("/downloads/cleanup", response_class=HTMLResponse)
async def cleanup_page(request: Request):
    return await _render(request, page=True)


@cleanup_router.post("/downloads/cleanup/duplicates", response_class=HTMLResponse)
async def remove_duplicates(request: Request, remove: list[int] = Form(default=[])):
    """Delete the chosen copies *with their files*; a group can never be emptied."""
    wanted = set(remove)
    try:
        groups = find_duplicates(await _torrents(request))
    except Exception as exc:
        return await _render(request, error=f"Transmission injoignable : {redact(str(exc))}")
    allowed: set[int] = set()
    for g in groups:
        ids = {c.torrent.id for c in g.items}
        if ids <= wanted:
            return await _render(request, error=f"« {g.title} » : garde au moins une copie.")
        allowed |= ids & wanted
    if not allowed:
        return await _render(request, error="Aucune copie selectionnee.")
    transmission = request.app.state.ctx.transmission
    failed = 0
    for torrent_id in sorted(allowed):
        try:
            await transmission.remove(torrent_id, delete_data=True)
        except Exception:
            failed += 1
    notice = f"{len(allowed) - failed} copie(s) supprimee(s) avec leurs fichiers."
    if failed:
        notice += f" {failed} echec(s)."
    return await _render(request, notice=notice)


@cleanup_router.post("/downloads/cleanup/errors", response_class=HTMLResponse)
async def handle_errors(request: Request, ids: list[int] = Form(default=[]), action: str = Form("")):
    """Stop, or remove from Transmission while keeping the files, torrents in error."""
    if action not in ("stop", "remove"):
        return await _render(request, error="Action inconnue.")
    try:
        in_error = {t.id for _, items in error_groups(await _torrents(request)) for t in items}
    except Exception as exc:
        return await _render(request, error=f"Transmission injoignable : {redact(str(exc))}")
    targets = sorted(set(ids) & in_error)
    transmission = request.app.state.ctx.transmission
    failed = 0
    for torrent_id in targets:
        try:
            if action == "stop":
                await transmission.pause(torrent_id)
            else:
                await transmission.remove(torrent_id, delete_data=False)
        except Exception:
            failed += 1
    done = len(targets) - failed
    verb = "arrete(s)" if action == "stop" else "retire(s) de Transmission (fichiers conserves)"
    notice = f"{done} torrent(s) {verb}." + (f" {failed} echec(s)." if failed else "")
    return await _render(request, notice=notice)
