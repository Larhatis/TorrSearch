from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from torsearch.models import Category
from torsearch.search.service import SearchService
from torsearch.transmission.client import TransmissionClient

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"categories": list(Category)}
    )


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", cat: str = "all"):
    service: SearchService = request.app.state.search_service
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    results = await service.search(q, category) if q.strip() else []
    return templates.TemplateResponse(
        request, "partials/results.html", {"results": results, "query": q}
    )


@router.post("/download", response_class=HTMLResponse)
async def download(request: Request, download_url: str = Form(...)):
    transmission: TransmissionClient = request.app.state.transmission
    try:
        torrent_id = transmission.add(download_url)
        message = f"Ajoute a Transmission (#{torrent_id})"
        ok = True
    except Exception as exc:
        message = f"Erreur Transmission : {exc}"
        ok = False
    return templates.TemplateResponse(
        request, "partials/toast.html", {"ok": ok, "message": message}
    )


@router.get("/trackers", response_class=HTMLResponse)
async def trackers(request: Request):
    service: SearchService = request.app.state.search_service
    return templates.TemplateResponse(
        request, "trackers.html", {"indexers": service.indexers}
    )


def create_app(search_service: SearchService, transmission: TransmissionClient) -> FastAPI:
    app = FastAPI(title="TorSearch")
    app.state.search_service = search_service
    app.state.transmission = transmission
    app.include_router(router)
    return app
