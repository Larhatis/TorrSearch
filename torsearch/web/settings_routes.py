from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import IndexerConfig, SearchConfig, TransmissionConfig
from torsearch.context import AppContext
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.settings.mutations import (
    SettingsError,
    add_indexer,
    remove_indexer,
    set_general,
    set_indexer_enabled,
    update_indexer,
)
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


@settings_router.post("/settings/indexers", response_class=HTMLResponse)
async def add_indexer_route(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    ctx: AppContext = request.app.state.ctx
    try:
        indexer = IndexerConfig(name=name, url=url, api_key=api_key, auth=auth, enabled=True)
        ctx.update_settings(add_indexer(ctx.config, indexer))
        return _list(request, ctx, notice=f"Tracker « {name} » ajoute.")
    except (ValidationError, SettingsError) as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/test", response_class=HTMLResponse)
async def test_indexer_route(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    try:
        indexer = TorznabIndexer(IndexerConfig(name=name, url=url, api_key=api_key, auth=auth))
    except ValidationError as exc:
        return _toast(request, False, f"Erreur : {exc}")
    ok, message = await indexer.test()
    return _toast(request, ok, f"{name} : {message}")


@settings_router.post("/settings/indexers/{name}", response_class=HTMLResponse)
async def update_indexer_route(
    request: Request,
    name: str,
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    ctx: AppContext = request.app.state.ctx
    form = await request.form()
    new_name = str(form.get("name", name))
    current = next((ix for ix in ctx.config.indexers if ix.name == name), None)
    enabled = current.enabled if current else True
    try:
        indexer = IndexerConfig(name=new_name, url=url, api_key=api_key, auth=auth, enabled=enabled)
        ctx.update_settings(update_indexer(ctx.config, name, indexer))
        return _list(request, ctx, notice="Tracker mis a jour.")
    except (ValidationError, SettingsError) as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/{name}/toggle", response_class=HTMLResponse)
async def toggle_indexer_route(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((ix for ix in ctx.config.indexers if ix.name == name), None)
    try:
        ctx.update_settings(set_indexer_enabled(ctx.config, name, not current.enabled if current else True))
        return _list(request, ctx)
    except SettingsError as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/{name}/delete", response_class=HTMLResponse)
async def delete_indexer_route(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_indexer(ctx.config, name))
        return _list(request, ctx, notice=f"Tracker « {name} » supprime.")
    except SettingsError as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")
