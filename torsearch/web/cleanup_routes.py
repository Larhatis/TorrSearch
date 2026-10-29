from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.library.cleanup import error_groups, find_duplicates, removal_is_safe
from torsearch.redact import redact
from torsearch.web.templating import templates

logger = logging.getLogger(__name__)

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
async def remove_duplicates(request: Request, remove: list[str] = Form(default=[])):
    """Delete the chosen copies *with their files*.

    Copies are designated by info hash (Transmission ids change when it restarts). Every
    group must keep covering what its complete copies covered, or nothing is deleted.
    """
    wanted = {h.lower() for h in remove if h}
    try:
        groups = find_duplicates(await _torrents(request))
    except Exception as exc:
        return await _render(request, error=f"Transmission injoignable : {redact(str(exc))}")
    targets = []
    for g in groups:
        chosen = {c.torrent.info_hash.lower() for c in g.items if c.torrent.info_hash.lower() in wanted}
        if not chosen:
            continue
        problem = removal_is_safe(g, chosen)
        if problem:
            return await _render(request, error=f"« {g.title} » : {problem}. Rien n'a ete supprime.")
        targets += [c.torrent for c in g.items if c.torrent.info_hash.lower() in chosen]
    if not targets:
        return await _render(request, error="Aucune copie selectionnee.")
    transmission = request.app.state.ctx.transmission
    failed = 0
    for t in targets:
        try:
            await transmission.remove(t.id, delete_data=True)
            logger.info("Menage : doublon supprime avec ses fichiers : %s", t.name)
        except Exception as exc:
            failed += 1
            logger.warning("Menage : suppression de '%s' impossible : %s", t.name, redact(str(exc)))
    notice = f"{len(targets) - failed} copie(s) supprimee(s) avec leurs fichiers."
    if failed:
        notice += f" {failed} echec(s), voir le journal."
    return await _render(request, notice=notice)


@cleanup_router.post("/downloads/cleanup/errors", response_class=HTMLResponse)
async def handle_errors(request: Request, hashes: list[str] = Form(default=[]), action: str = Form("")):
    """Stop, or remove from Transmission while keeping the files, torrents in error."""
    if action not in ("stop", "remove"):
        return await _render(request, error="Action inconnue.")
    wanted = {h.lower() for h in hashes if h}
    try:
        in_error = [t for _, items in error_groups(await _torrents(request)) for t in items]
    except Exception as exc:
        return await _render(request, error=f"Transmission injoignable : {redact(str(exc))}")
    targets = [t for t in in_error if t.info_hash and t.info_hash.lower() in wanted]
    transmission = request.app.state.ctx.transmission
    failed = 0
    for t in targets:
        try:
            if action == "stop":
                await transmission.pause(t.id)
            else:
                await transmission.remove(t.id, delete_data=False)
        except Exception as exc:
            failed += 1
            logger.warning("Menage : action '%s' sur '%s' impossible : %s", action, t.name, redact(str(exc)))
    done = len(targets) - failed
    verb = "arrete(s)" if action == "stop" else "retire(s) de Transmission (fichiers conserves)"
    notice = f"{done} torrent(s) {verb}." + (f" {failed} echec(s), voir le journal." if failed else "")
    return await _render(request, notice=notice)
