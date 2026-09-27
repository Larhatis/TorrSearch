from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from torsearch.web.authz import require_member
from torsearch.web.templating import templates

movie_router = APIRouter()


@movie_router.get("/movies/{tmdb_id}", response_class=HTMLResponse)
@movie_router.get("/movies/{tmdb_id}/detail", response_class=HTMLResponse)
async def movie_detail(request: Request, tmdb_id: int):
    ctx = request.app.state.ctx
    library = request.app.state.library
    movie = library.get(tmdb_id) if library else None

    # Fetch TMDB details
    tmdb_details = await ctx.tmdb.get_details("movie", tmdb_id)
    if movie is None and tmdb_details is None:
        raise HTTPException(status_code=404, detail="Film introuvable")

    title = movie.title if movie else (tmdb_details.title if tmdb_details else "")
    orig_from_lib = movie.original_title if movie else None
    orig_from_tmdb = tmdb_details.original_title if tmdb_details else None
    original_title = orig_from_lib or orig_from_tmdb
    year = (movie.year if movie else None) or (tmdb_details.year if tmdb_details else None)
    poster_path = (movie.poster_path if movie else None) or (tmdb_details.poster_path if tmdb_details else None)
    overview = tmdb_details.overview if tmdb_details else ""
    poster_url = f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None

    # Jellyfin presence
    owned = await ctx.jellyfin.owned()
    jf_item_id = owned.get(f"movie:{tmdb_id}")
    jf_enabled = getattr(ctx.jellyfin, "enabled", False)
    if not jf_item_id and jf_enabled and hasattr(ctx.jellyfin, "find_matching"):
        match = await ctx.jellyfin.find_matching(title)
        if match and getattr(match, "media_type", None) == "movie":
            jf_item_id = match.id

    template_data = {
        "movie": {
            "tmdb_id": tmdb_id,
            "title": title,
            "original_title": original_title,
            "year": year,
            "poster_path": poster_path,
            "poster_url": poster_url,
            "overview": overview,
            "in_library": movie is not None,
            "status": movie.status if movie else "wanted",
            "grabbed_title": movie.grabbed_title if movie else None,
            "grabbed_at": movie.grabbed_at if movie else None,
        },
        "owned_jf": jf_item_id,
        "jellyfin_url": ctx.jellyfin.base_url,
    }

    is_modal = request.headers.get("HX-Request") == "true" or request.url.path.endswith("/detail")
    template_name = "partials/movie_detail_modal.html" if is_modal else "movie_detail.html"
    return templates.TemplateResponse(request, template_name, template_data)


@movie_router.post("/movies/{tmdb_id}/regrab", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def movie_regrab(request: Request, tmdb_id: int):
    library = request.app.state.library
    if library:
        library.unmark_grabbed(tmdb_id)

    badge = (
        '<div id="movie-action-btn" '
        'class="flex items-center gap-1.5 rounded-lg border border-sky-500/30 '
        'bg-sky-600/20 px-3.5 py-2 text-xs font-semibold text-sky-300">'
        '<i class="ti ti-check"></i> Remis en recherche active</div>'
    )
    toast = (
        '<div id="toast" hx-swap-oob="innerHTML">'
        '<div class="rounded bg-sky-600 px-3 py-2 text-sm text-white shadow-lg">'
        'Film remis en recherche active pour une meilleure release.'
        '</div></div>'
    )
    return HTMLResponse(content=f"{badge}{toast}")
