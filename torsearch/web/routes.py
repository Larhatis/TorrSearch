from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from torsearch import __version__
from torsearch.context import AppContext
from torsearch.library.sending import send_release
from torsearch.models import Category
from torsearch.search.filters import VALID_DIRECTIONS, VALID_SORTS, ResultFilters, apply
from torsearch.search.result_cache import ResultCache
from torsearch.web.auth import (
    AuthMiddleware,
    AuthSettings,
    CrossSiteGuardMiddleware,
    LoginThrottle,
    SecurityHeadersMiddleware,
)
from torsearch.web.auth_routes import auth_router
from torsearch.web.authz import effective_role, require_admin, require_member
from torsearch.web.calendar_routes import calendar_router
from torsearch.web.claude_routes import claude_router
from torsearch.web.cleanup_routes import cleanup_router
from torsearch.web.discover_routes import discover_router
from torsearch.web.downloads_routes import downloads_router
from torsearch.web.forms import GB, split_words, to_int, to_size_bytes
from torsearch.web.library_routes import library_router
from torsearch.web.movie_routes import movie_router
from torsearch.web.requests_routes import requests_router
from torsearch.web.series_routes import series_router
from torsearch.web.settings_routes import settings_router
from torsearch.web.surveillance_routes import surveillance_router
from torsearch.web.templating import STATIC_DIR, templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Liveness probe for Docker's HEALTHCHECK (public, no data)."""
    return JSONResponse({"status": "ok", "version": __version__})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "", cat: str = "all"):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "categories": list(Category),
            "has_trackers": bool(ctx.config.indexers),
            "q": q,
            "cat": cat,
        },
    )


def _active_filters(filters: ResultFilters) -> list[dict]:
    chips: list[dict] = []
    if filters.min_seeders > 0:
        chips.append({"label": f"Seeders ≥ {filters.min_seeders}", "name": "min_seeders"})
    if filters.min_size is not None:
        chips.append({"label": f"≥ {round(filters.min_size / GB, 1)} Go", "name": "min_size_gb"})
    if filters.max_size is not None:
        chips.append({"label": f"≤ {round(filters.max_size / GB, 1)} Go", "name": "max_size_gb"})
    for q in filters.qualities:
        chips.append({"label": q, "name": "quality", "value": q})
    if filters.exclude:
        chips.append({"label": "exclut : " + ", ".join(filters.exclude), "name": "exclude"})
    return chips


@router.get("/search", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def search(
    request: Request,
    q: str = "",
    cat: str = "all",
    min_seeders: str = "0",
    min_size_gb: str = "",
    max_size_gb: str = "",
    quality: list[str] = Query(default=[]),
    exclude: str = "",
    sort: str = "relevance",
    dir: str = "desc",
):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    raw = await ctx.search_service.search(q, category) if q.strip() else []

    effective_sort = sort if sort in VALID_SORTS else "relevance"
    effective_dir = dir if dir in VALID_DIRECTIONS else "desc"
    filters = ResultFilters(
        min_seeders=max(to_int(min_seeders), 0),
        min_size=to_size_bytes(min_size_gb),
        max_size=to_size_bytes(max_size_gb),
        qualities=[item for item in quality if item],
        exclude=split_words(exclude),
        sort=effective_sort,
        direction=effective_dir,
        query=q,
    )
    results = apply(raw, filters)
    sources = [ix.name for ix in ctx.config.indexers if ix.enabled]
    jellyfin_matches = []
    if getattr(ctx, "jellyfin", None) and ctx.jellyfin.enabled and q.strip():
        if hasattr(ctx.jellyfin, "find_matches"):
            jellyfin_matches = await ctx.jellyfin.find_matches(q, limit=6)
        elif hasattr(ctx.jellyfin, "find_matching"):
            one = await ctx.jellyfin.find_matching(q)
            if one is not None:
                jellyfin_matches = [one]
    tmdb_matches = []
    if not results and q.strip() and getattr(ctx, "tmdb", None) and getattr(ctx.tmdb, "enabled", False):
        try:
            tmdb_res = await ctx.tmdb.search(q.strip())
            if cat == "movies":
                tmdb_matches = [m for m in tmdb_res if m.media_type == "movie"][:3]
            elif cat == "tv":
                tmdb_matches = [m for m in tmdb_res if m.media_type == "tv"][:3]
            else:
                tmdb_matches = [m for m in tmdb_res if m.media_type in ("movie", "tv")][:3]
        except Exception:
            pass

    library = getattr(request.app.state, "library", None)
    series_library = getattr(request.app.state, "series_library", None)
    movie_ids = {m.tmdb_id for m in library.list()} if library else set()
    series_ids = {s.tmdb_id for s in series_library.list()} if series_library else set()

    cache: ResultCache = request.app.state.result_cache
    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "results": results,
            "result_ids": [cache.put(r) for r in results],
            "query": q,
            "cat": cat,
            "sort": effective_sort,
            "dir": effective_dir,
            "active_filters": _active_filters(filters),
            "sources": sources,
            "jellyfin_matches": jellyfin_matches,
            "jellyfin_match": jellyfin_matches[0] if jellyfin_matches else None,
            "jellyfin_url": ctx.jellyfin.base_url if getattr(ctx, "jellyfin", None) else "",
            "tmdb_matches": tmdb_matches,
            "tmdb_movies": tmdb_matches,
            "movie_ids": movie_ids,
            "series_ids": series_ids,
            "library_ids": movie_ids,
        },
    )


@router.post("/download", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def download(
    request: Request,
    result_id: str = Form(""),
    download_url: str = Form(""),
    category: str = Form(""),
    title: str = Form(""),
):
    tracker_hash = ""
    if result_id:
        # Members only ever hold this opaque id: the tracker URL (passkey) stays server-side.
        cached = request.app.state.result_cache.get(result_id)
        if cached is None:
            return templates.TemplateResponse(request, "partials/toast.html", {
                "ok": False, "message": "Resultat expire : relance la recherche."})
        download_url, title, category = cached.download_url, cached.title, cached.category.value
        tracker_hash = cached.infohash or ""
    elif not download_url:
        return templates.TemplateResponse(request, "partials/toast.html", {
            "ok": False, "message": "Aucun torrent indique."})
    elif effective_role(request) != "admin":
        raise HTTPException(status_code=403, detail="Acces refuse")
    try:
        cat = Category(category)
    except ValueError:
        cat = Category.OTHER

    out = await send_release(request.app.state, download_url, title, cat, fallback_hash=tracker_hash or None)
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": out.ok, "message": out.message})


def create_app(
    ctx: AppContext, history=None, monitor=None, auth: AuthSettings | None = None, library=None,
    series_library=None, users=None, requests_store=None, blacklist=None, db=None, log_handler=None,
    grabs=None, public_url: str | None = None, claude_provider=None,
) -> FastAPI:
    if auth is None:
        auth = AuthSettings(enabled=False)
    claude: dict = {}  # the MCP server, once built (its session manager runs with the app)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            if "server" in claude:
                await stack.enter_async_context(claude["server"].session_manager.run())
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
    app.state.monitor = monitor
    app.state.auth = auth
    app.state.library = library
    app.state.series_library = series_library
    app.state.users = users
    app.state.requests = requests_store
    app.state.blacklist = blacklist
    app.state.grabs = grabs
    app.state.db = db
    app.state.log_handler = log_handler
    app.state.login_throttle = LoginThrottle()
    app.state.result_cache = ResultCache()
    app.state.claude_provider = claude_provider if public_url and auth.enabled else None
    app.state.claude_public_url = public_url if public_url and auth.enabled else None
    app.add_middleware(CrossSiteGuardMiddleware)  # always on, even without auth
    app.add_middleware(SecurityHeadersMiddleware)
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
    app.include_router(settings_router, dependencies=[Depends(require_admin)])
    app.include_router(cleanup_router, dependencies=[Depends(require_admin)])  # deletes files
    app.include_router(downloads_router, dependencies=[Depends(require_member)])
    app.include_router(surveillance_router, dependencies=[Depends(require_admin)])
    app.include_router(auth_router)
    app.include_router(discover_router)
    app.include_router(library_router)
    app.include_router(movie_router)
    app.include_router(series_router)
    app.include_router(requests_router)
    app.include_router(calendar_router)
    app.include_router(claude_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if public_url:
        _mount_claude(app, public_url, auth, claude_provider, claude)
    return app


_AUTH_REQUIRED = "Activez l'authentification (TORSEARCH_USERNAME / TORSEARCH_PASSWORD) pour utiliser Claude."


def _mount_claude(app: FastAPI, public_url: str, auth: AuthSettings, provider, claude: dict) -> None:
    """Claude's MCP connector: the SDK app (OAuth routes + /mcp) goes last, after every route."""
    if not auth.enabled or provider is None:
        async def disabled(request: Request):
            return JSONResponse({"error": _AUTH_REQUIRED}, status_code=503)

        app.add_api_route("/mcp", disabled, methods=["GET", "POST", "DELETE"], include_in_schema=False)
        logger.warning("Claude : connecteur desactive, %s", _AUTH_REQUIRED)
        return
    from mcp.server.auth.settings import AuthSettings as McpAuthSettings
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
    from mcp.server.transport_security import TransportSecuritySettings

    from torsearch.claude.oauth import SCOPE
    from torsearch.claude.server import build_claude_server

    mcp_auth = McpAuthSettings(
        issuer_url=public_url, resource_server_url=f"{public_url}/mcp", validate_token_resource=False,
        required_scopes=[SCOPE],
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE],
                                                              default_scopes=[SCOPE]),
        revocation_options=RevocationOptions(enabled=True),
    )
    server = build_claude_server(app.state, auth=mcp_auth, provider=provider)
    sub = server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True, host="0.0.0.0",
        # The public host is the tunnel's; requests reach the app through it, not via a browser.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    claude["server"] = server
    app.mount("/", sub)
    logger.info("Claude : connecteur MCP actif sur %s/mcp", public_url)
