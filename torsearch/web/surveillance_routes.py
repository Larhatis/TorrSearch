from __future__ import annotations

import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import Category, MonitorConfig, SavedSearch
from torsearch.context import AppContext
from torsearch.settings.mutations import (
    SettingsError,
    add_saved_search,
    remove_saved_search,
    set_monitor,
    set_saved_search_enabled,
)
from torsearch.web.templating import templates

surveillance_router = APIRouter()

_GB = 1024 ** 3


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_size_bytes(value: str) -> int | None:
    try:
        gb = float(value)
    except (TypeError, ValueError):
        return None
    return int(gb * _GB) if gb > 0 else None


def _context(request: Request, error=None, notice=None):
    ctx: AppContext = request.app.state.ctx
    history = request.app.state.history
    records = history.records() if history is not None else []
    return {
        "config": ctx.config, "searches": ctx.config.saved_searches,
        "monitor": ctx.config.monitor, "records": records,
        "categories": list(Category), "error": error, "notice": notice,
    }


def _page(request, **kw):
    return templates.TemplateResponse(request, "surveillance.html", _context(request, **kw))


def _body(request, **kw):
    return templates.TemplateResponse(request, "partials/surveillance_body.html", _context(request, **kw))


@surveillance_router.get("/surveillance", response_class=HTMLResponse)
async def page(request: Request):
    return _page(request)


@surveillance_router.post("/surveillance/monitor", response_class=HTMLResponse)
async def update_monitor(request: Request, enabled: str | None = Form(None), interval_minutes: str = Form("30")):
    ctx: AppContext = request.app.state.ctx
    try:
        monitor = MonitorConfig(enabled=enabled is not None, interval_minutes=interval_minutes)
        ctx.update_settings(set_monitor(ctx.config, monitor))
        return _body(request, notice="Surveillance mise a jour.")
    except (ValidationError, SettingsError) as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches", response_class=HTMLResponse)
async def add_search(
    request: Request,
    name: str = Form(...),
    query: str = Form(...),
    cat: str = Form("all"),
    mode: str = Form("auto"),
    min_seeders: str = Form("0"),
    min_size_gb: str = Form(""),
    max_size_gb: str = Form(""),
    quality: list[str] = Form(default=[]),
    exclude: str = Form(""),
):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    try:
        saved = SavedSearch(
            name=name, query=query, category=category, mode=mode,
            min_seeders=max(_to_int(min_seeders), 0),
            min_size=_to_size_bytes(min_size_gb),
            max_size=_to_size_bytes(max_size_gb),
            qualities=[q for q in quality if q],
            exclude=[w for w in re.split(r"[\s,]+", exclude) if w],
        )
        ctx.update_settings(add_saved_search(ctx.config, saved))
        return _body(request, notice=f"Recherche « {name} » enregistree.")
    except (ValidationError, SettingsError) as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/toggle", response_class=HTMLResponse)
async def toggle_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((s for s in ctx.config.saved_searches if s.name == name), None)
    try:
        ctx.update_settings(
            set_saved_search_enabled(ctx.config, name, not current.enabled if current else True)
        )
        return _body(request)
    except SettingsError as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/delete", response_class=HTMLResponse)
async def delete_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_saved_search(ctx.config, name))
        return _body(request, notice=f"Recherche « {name} » supprimee.")
    except SettingsError as exc:
        return _body(request, error=f"Erreur : {exc}")
