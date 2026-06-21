from __future__ import annotations

import re
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from torsearch.context import AppContext
from torsearch.models import Category
from torsearch.web.auth import AuthMiddleware, AuthSettings
from torsearch.web.auth_routes import auth_router
from torsearch.web.discover_routes import discover_router
from torsearch.web.library_routes import library_router
from torsearch.web.series_routes import series_router
from torsearch.search.filters import VALID_DIRECTIONS, VALID_SORTS, ResultFilters, apply
from torsearch.web.downloads_routes import downloads_router
from torsearch.web.settings_routes import settings_router
from torsearch.web.surveillance_routes import surveillance_router
from torsearch.web.templating import templates

router = APIRouter()

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


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(
        request,
        "index.html",
        {"categories": list(Category), "has_trackers": bool(ctx.config.indexers)},
    )


def _active_filters(filters: ResultFilters) -> list[dict]:
    chips: list[dict] = []
    if filters.min_seeders > 0:
        chips.append({"label": f"Seeders ≥ {filters.min_seeders}", "name": "min_seeders"})
    if filters.min_size is not None:
        chips.append({"label": f"≥ {round(filters.min_size / _GB, 1)} Go", "name": "min_size_gb"})
    if filters.max_size is not None:
        chips.append({"label": f"≤ {round(filters.max_size / _GB, 1)} Go", "name": "max_size_gb"})
    for q in filters.qualities:
        chips.append({"label": q, "name": "quality", "value": q})
    if filters.exclude:
        chips.append({"label": "exclut : " + ", ".join(filters.exclude), "name": "exclude"})
    return chips


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    cat: str = "all",
    min_seeders: str = "0",
    min_size_gb: str = "",
    max_size_gb: str = "",
    quality: list[str] = Query(default=[]),
    exclude: str = "",
    sort: str = "seeders",
    dir: str = "desc",
):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    raw = await ctx.search_service.search(q, category) if q.strip() else []

    effective_sort = sort if sort in VALID_SORTS else "seeders"
    effective_dir = dir if dir in VALID_DIRECTIONS else "desc"
    filters = ResultFilters(
        min_seeders=max(_to_int(min_seeders), 0),
        min_size=_to_size_bytes(min_size_gb),
        max_size=_to_size_bytes(max_size_gb),
        qualities=[item for item in quality if item],
        exclude=[w for w in re.split(r"[\s,]+", exclude) if w],
        sort=effective_sort,
        direction=effective_dir,
    )
    results = apply(raw, filters)
    sources = [ix.name for ix in ctx.config.indexers if ix.enabled]
    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "results": results,
            "query": q,
            "sort": effective_sort,
            "dir": effective_dir,
            "active_filters": _active_filters(filters),
            "sources": sources,
        },
    )


@router.post("/download", response_class=HTMLResponse)
async def download(request: Request, download_url: str = Form(...)):
    ctx: AppContext = request.app.state.ctx
    try:
        torrent_id = ctx.transmission.add(download_url)
        message, ok = f"Ajoute a Transmission (#{torrent_id})", True
    except Exception as exc:
        message, ok = f"Erreur Transmission : {exc}", False
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})


def create_app(
    ctx: AppContext, history=None, monitor=None, auth: AuthSettings | None = None, library=None,
    series_library=None,
) -> FastAPI:
    if auth is None:
        auth = AuthSettings(enabled=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if monitor is not None:
            await monitor.start()
        try:
            yield
        finally:
            if monitor is not None:
                await monitor.stop()

    app = FastAPI(title="TorrSearch", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.history = history
    app.state.auth = auth
    app.state.library = library
    app.state.series_library = series_library
    if auth.enabled:
        app.add_middleware(AuthMiddleware, settings=auth)
        app.add_middleware(
            SessionMiddleware,
            secret_key=auth.secret_key,
            https_only=auth.https_only,
            same_site="lax",
            max_age=60 * 60 * 24 * 14,
        )
    app.include_router(router)
    app.include_router(settings_router)
    app.include_router(downloads_router)
    app.include_router(surveillance_router)
    app.include_router(auth_router)
    app.include_router(discover_router)
    app.include_router(library_router)
    app.include_router(series_router)
    return app
