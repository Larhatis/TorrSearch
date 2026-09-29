from __future__ import annotations

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
from torsearch.web.forms import split_words, to_int, to_size_bytes
from torsearch.web.templating import templates

surveillance_router = APIRouter()


async def _get_context(request: Request, error=None, notice=None):
    ctx: AppContext = request.app.state.ctx
    history = getattr(request.app.state, "history", None)
    records = history.records() if history is not None else []
    runner = getattr(request.app.state, "monitor", None)

    library = getattr(request.app.state, "library", None)
    series_library = getattr(request.app.state, "series_library", None)
    movies = library.list() if library is not None else []
    series = series_library.list() if series_library is not None else []

    owned: dict[str, str] = {}
    jf = getattr(ctx, "jellyfin", None)
    if jf and getattr(jf, "enabled", False) and hasattr(jf, "owned"):
        try:
            owned = await jf.owned()
        except Exception:
            pass

    jellyfin_url = ctx.jellyfin.base_url if getattr(ctx, "jellyfin", None) else ""

    return {
        "config": ctx.config,
        "searches": ctx.config.saved_searches,
        "monitor": ctx.config.monitor,
        "records": records,
        "categories": list(Category),
        "error": error,
        "notice": notice,
        "runner": runner,
        "movies": movies,
        "series": series,
        "owned": owned,
        "jellyfin_url": jellyfin_url,
    }


async def _page(request, **kw):
    data = await _get_context(request, **kw)
    return templates.TemplateResponse(request, "surveillance.html", data)


async def _body(request, **kw):
    data = await _get_context(request, **kw)
    return templates.TemplateResponse(request, "partials/surveillance_body.html", data)


@surveillance_router.get("/surveillance", response_class=HTMLResponse)
async def page(request: Request):
    if request.headers.get("HX-Request"):
        return await _body(request)
    return await _page(request)


@surveillance_router.get("/surveillance/history", response_class=HTMLResponse)
async def history_list(request: Request):
    data = await _get_context(request)
    return templates.TemplateResponse(request, "partials/surveillance_history.html", data)


@surveillance_router.post("/surveillance/monitor", response_class=HTMLResponse)
async def update_monitor(request: Request, enabled: str | None = Form(None), interval_minutes: str = Form("30")):
    ctx: AppContext = request.app.state.ctx
    try:
        monitor = MonitorConfig.model_validate({
            **ctx.config.monitor.model_dump(),
            "enabled": enabled is not None,
            "interval_minutes": interval_minutes,
        })
        if monitor.interval_minutes < 1:
            raise SettingsError("l'intervalle doit etre d'au moins 1 minute.")
        ctx.update_settings(set_monitor(ctx.config, monitor))
        runner = getattr(request.app.state, "monitor", None)
        if runner is not None:
            runner.wake()
        return await _body(request, notice="Surveillance mise a jour.")
    except (ValidationError, SettingsError) as exc:
        return await _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/run-now", response_class=HTMLResponse)
async def run_now(request: Request):
    ctx: AppContext = request.app.state.ctx
    if not ctx.config.monitor.enabled:
        return await _body(request, error="Active d'abord la surveillance globale (coche la case et enregistre).")
    runner = getattr(request.app.state, "monitor", None)
    if runner is not None:
        try:
            records = await runner.run_once()
            count = len(records)
            if count > 0:
                notice = f"Verification effectuee : {count} nouveau(x) torrent(s) envoye(s) a Transmission."
            else:
                notice = (
                    "Verification effectuee : aucun nouvel element a recuperer "
                    "(les torrents/episodes sont deja presents dans Transmission ou sur le disque)."
                )
        except Exception as exc:
            return await _body(request, error=f"Erreur lors de la verification : {exc}")
    else:
        notice = "Module de surveillance non disponible."
    return await _body(request, notice=notice)


@surveillance_router.post("/surveillance/history/clear", response_class=HTMLResponse)
async def clear_history(request: Request):
    history = request.app.state.history
    if history is not None:
        history.clear()
    return await _body(request, notice="Historique vide.")


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
            min_seeders=max(to_int(min_seeders), 0),
            min_size=to_size_bytes(min_size_gb),
            max_size=to_size_bytes(max_size_gb),
            qualities=[q for q in quality if q],
            exclude=split_words(exclude),
        )
        ctx.update_settings(add_saved_search(ctx.config, saved))
        return await _body(request, notice=f"Recherche « {name} » enregistree.")
    except (ValidationError, SettingsError) as exc:
        return await _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/toggle", response_class=HTMLResponse)
async def toggle_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((s for s in ctx.config.saved_searches if s.name == name), None)
    try:
        ctx.update_settings(
            set_saved_search_enabled(ctx.config, name, not current.enabled if current else True)
        )
        return await _body(request)
    except SettingsError as exc:
        return await _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/delete", response_class=HTMLResponse)
async def delete_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_saved_search(ctx.config, name))
        return await _body(request, notice=f"Recherche « {name} » supprimee.")
    except SettingsError as exc:
        return await _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/movies/{tmdb_id}/remove", response_class=HTMLResponse)
async def surveillance_movie_remove(request: Request, tmdb_id: int):
    library = getattr(request.app.state, "library", None)
    if library is not None:
        library.remove(tmdb_id)
    return await _body(request, notice="Film retire de la surveillance.")


@surveillance_router.post("/surveillance/series/{tmdb_id}/remove", response_class=HTMLResponse)
async def surveillance_series_remove(request: Request, tmdb_id: int):
    series_library = getattr(request.app.state, "series_library", None)
    if series_library is not None:
        series_library.remove(tmdb_id)
    return await _body(request, notice="Serie retiree de la surveillance.")


@surveillance_router.post("/surveillance/movies/{tmdb_id}/regrab", response_class=HTMLResponse)
async def surveillance_movie_regrab(request: Request, tmdb_id: int):
    library = getattr(request.app.state, "library", None)
    if library is not None:
        library.unmark_grabbed(tmdb_id)
        runner = getattr(request.app.state, "monitor", None)
        if runner is not None:
            runner.wake()
        return await _body(request, notice="Film remis en recherche active.")
    return await _body(request)


@surveillance_router.post("/surveillance/quick-add", response_class=HTMLResponse)
async def quick_add_search(
    request: Request,
    query: str = Form(...),
    cat: str = Form("movies"),
    name: str = Form(""),
):
    ctx: AppContext = request.app.state.ctx
    search_name = name.strip() or query.strip()
    try:
        category = Category(cat)
    except ValueError:
        category = Category.MOVIES
    try:
        saved = SavedSearch(
            name=search_name,
            query=query.strip(),
            category=category,
            mode="auto",
            min_seeders=0,
            qualities=[],
            exclude=["cam", "ts"],
        )
        new_config = add_saved_search(ctx.config, saved)
        if not new_config.monitor.enabled:
            new_config = set_monitor(new_config, new_config.monitor.model_copy(update={"enabled": True}))
        ctx.update_settings(new_config)
        runner = getattr(request.app.state, "monitor", None)
        if runner is not None:
            runner.wake()

        badge = (
            '<div class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/10 '
            'border border-emerald-500/20 px-3 py-1.5 text-xs text-emerald-400 font-medium">'
            '<i class="ti ti-check"></i> En surveillance (auto-download)</div>'
        )
        toast = (
            f'<div id="toast" hx-swap-oob="innerHTML">'
            f'<div class="rounded bg-emerald-600 px-3 py-2 text-sm text-white shadow-lg">'
            f'« {search_name} » sera telecharge automatiquement des sa premiere sortie en torrent.'
            f'</div></div>'
        )
        return HTMLResponse(content=f"{badge}{toast}")
    except SettingsError:
        badge = (
            '<div class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/10 '
            'border border-emerald-500/20 px-3 py-1.5 text-xs text-emerald-400 font-medium">'
            '<i class="ti ti-check"></i> Deja en surveillance</div>'
        )
        return HTMLResponse(content=badge)
    except ValidationError as exc:
        badge = f'<div class="text-xs text-red-400">{exc}</div>'
        return HTMLResponse(content=badge)
