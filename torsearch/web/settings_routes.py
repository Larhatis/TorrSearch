from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import (
    IndexerConfig,
    JellyfinConfig,
    LibraryConfig,
    NotificationChannel,
    PathsConfig,
    SearchConfig,
    TransmissionConfig,
)
from torsearch.context import AppContext
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.models import Category
from torsearch.notifications.notifier import Notifier
from torsearch.settings.mutations import (
    SettingsError,
    add_channel,
    add_indexer,
    remove_channel,
    remove_indexer,
    set_channel_enabled,
    set_general,
    set_indexer_enabled,
    set_jellyfin,
    set_library,
    set_paths,
    update_indexer,
)
from torsearch.users.store import Role, UserError
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
    users = getattr(request.app.state, "users", None)
    return templates.TemplateResponse(
        request, "settings.html", {
            "config": ctx.config, "indexers": ctx.config.indexers,
            "channels": ctx.config.notifications, "categories": list(Category),
            "users": users.list() if users else [],
        }
    )


def _user_list(request: Request, error: str | None = None, notice: str | None = None):
    users = getattr(request.app.state, "users", None)
    return templates.TemplateResponse(
        request, "partials/user_list.html",
        {"users": users.list() if users else [], "error": error, "notice": notice},
    )


@settings_router.post("/settings/users", response_class=HTMLResponse)
async def add_user_route(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("guest"),
):
    users = request.app.state.users
    try:
        users.add(username.strip(), password, Role(role))
        return _user_list(request, notice=f"Utilisateur « {username} » ajoute.")
    except (UserError, ValueError) as exc:
        return _user_list(request, error=f"Erreur : {exc}")


@settings_router.post("/settings/users/{username}/role", response_class=HTMLResponse)
async def set_user_role_route(request: Request, username: str, role: str = Form(...)):
    users = request.app.state.users
    try:
        users.set_role(username, Role(role))
        return _user_list(request, notice="Role mis a jour.")
    except (UserError, ValueError) as exc:
        return _user_list(request, error=f"Erreur : {exc}")


@settings_router.post("/settings/users/{username}/delete", response_class=HTMLResponse)
async def delete_user_route(request: Request, username: str):
    users = request.app.state.users
    try:
        users.remove(username)
        return _user_list(request, notice=f"Utilisateur « {username} » supprime.")
    except UserError as exc:
        return _user_list(request, error=f"Erreur : {exc}")


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


@settings_router.post("/settings/library", response_class=HTMLResponse)
async def update_library(
    request: Request,
    quality: list[str] = Form(default=[]),
    min_seeders: str = Form("1"),
    upgrades: str | None = Form(None),
):
    ctx: AppContext = request.app.state.ctx
    try:
        profile = LibraryConfig(
            qualities=[q for q in quality if q],
            min_seeders=int(min_seeders) if min_seeders.lstrip("-").isdigit() else 0,
            upgrades=upgrades is not None,
        )
        ctx.update_settings(set_library(ctx.config, profile))
        return _toast(request, True, "Profil bibliotheque enregistre.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")


@settings_router.post("/settings/jellyfin", response_class=HTMLResponse)
async def update_jellyfin(request: Request, url: str = Form(""), api_key: str = Form("")):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(set_jellyfin(ctx.config, JellyfinConfig(url=url, api_key=api_key)))
        return _toast(request, True, "Jellyfin enregistre.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")


@settings_router.post("/settings/paths", response_class=HTMLResponse)
async def update_paths(request: Request):
    ctx: AppContext = request.app.state.ctx
    form = await request.form()
    by_category = {}
    for c in Category:
        if c == Category.ALL:
            continue
        value = str(form.get(f"path_{c.value}") or "").strip()
        if value:
            by_category[c.value] = value
    try:
        ctx.update_settings(set_paths(ctx.config, PathsConfig(by_category=by_category)))
        return _toast(request, True, "Dossiers enregistres.")
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


def _notif_list(request: Request, ctx: AppContext, error: str | None = None, notice: str | None = None):
    return templates.TemplateResponse(
        request, "partials/notification_list.html",
        {"channels": ctx.config.notifications, "error": error, "notice": notice},
    )


@settings_router.post("/settings/notifications", response_class=HTMLResponse)
async def add_notification(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    url: str = Form(""),
    token: str = Form(""),
    chat_id: str = Form(""),
):
    ctx: AppContext = request.app.state.ctx
    try:
        channel = NotificationChannel(name=name, type=type, url=url, token=token, chat_id=chat_id)
        ctx.update_settings(add_channel(ctx.config, channel))
        return _notif_list(request, ctx, notice=f"Canal « {name} » ajoute.")
    except (ValidationError, SettingsError) as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/toggle", response_class=HTMLResponse)
async def toggle_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((c for c in ctx.config.notifications if c.name == name), None)
    try:
        ctx.update_settings(set_channel_enabled(ctx.config, name, not current.enabled if current else True))
        return _notif_list(request, ctx)
    except SettingsError as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/delete", response_class=HTMLResponse)
async def delete_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_channel(ctx.config, name))
        return _notif_list(request, ctx, notice=f"Canal « {name} » supprime.")
    except SettingsError as exc:
        return _notif_list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/notifications/{name}/test", response_class=HTMLResponse)
async def test_notification(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    channel = next((c for c in ctx.config.notifications if c.name == name), None)
    if channel is None:
        return _toast(request, False, "Canal introuvable.")
    ok, message = await Notifier().test(channel)
    return _toast(request, ok, f"{name} : {message}")
