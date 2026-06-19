from __future__ import annotations

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.models import Category
from torsearch.web.settings_routes import settings_router
from torsearch.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"categories": list(Category)})


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", cat: str = "all"):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    results = await ctx.search_service.search(q, category) if q.strip() else []
    return templates.TemplateResponse(request, "partials/results.html", {"results": results, "query": q})


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
    return app
