from __future__ import annotations

import re

from fastapi import APIRouter, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.models import Category
from torsearch.search.filters import VALID_DIRECTIONS, VALID_SORTS, ResultFilters, apply
from torsearch.web.downloads_routes import downloads_router
from torsearch.web.settings_routes import settings_router
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
    return templates.TemplateResponse(request, "index.html", {"categories": list(Category)})


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
    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {"results": results, "query": q, "sort": effective_sort, "dir": effective_dir},
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


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="TorSearch")
    app.state.ctx = ctx
    app.include_router(router)
    app.include_router(settings_router)
    app.include_router(downloads_router)
    return app
