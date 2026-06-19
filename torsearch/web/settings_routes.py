from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import SearchConfig, TransmissionConfig
from torsearch.context import AppContext
from torsearch.settings.mutations import SettingsError, set_general
from torsearch.web.templating import templates

settings_router = APIRouter()


def _toast(request: Request, ok: bool, message: str):
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})


def _list(request: Request, ctx: AppContext, error: str | None = None, notice: str | None = None):
    return templates.TemplateResponse(
        request, "partials/indexer_list.html",
        {"indexers": ctx.config.indexers, "error": error, "notice": notice},
    )


@settings_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(
        request, "settings.html", {"config": ctx.config, "indexers": ctx.config.indexers}
    )


@settings_router.post("/settings/general", response_class=HTMLResponse)
async def update_general(
    request: Request,
    host: str = Form(...),
    port: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    https: str | None = Form(None),
    timeout_seconds: str = Form(...),
):
    ctx: AppContext = request.app.state.ctx
    try:
        transmission = TransmissionConfig(
            host=host, port=port, username=username, password=password, https=https is not None
        )
        search = SearchConfig(timeout_seconds=timeout_seconds)
        ctx.update_settings(set_general(ctx.config, transmission, search))
        return _toast(request, True, "Reglages enregistres.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
