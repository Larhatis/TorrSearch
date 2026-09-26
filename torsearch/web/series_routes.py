from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedSeries
from torsearch.web.authz import require_member
from torsearch.web.templating import templates

series_router = APIRouter()


@series_router.post("/series/add", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def series_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    original_title: str = Form(""),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    series_library = request.app.state.series_library
    added = series_library.add(WantedSeries(
        tmdb_id=tmdb_id, title=title, original_title=original_title or None,
        year=year or None, poster_path=poster_path or None,
        added_at=datetime.now(UTC),
    ))
    message = "Serie suivie." if added else "Serie deja suivie."
    if request.headers.get("HX-Target", "").startswith("media-action-"):
        badge = (
            f'<div id="media-action-tv-{tmdb_id}" '
            f'class="mt-1.5 flex w-full items-center justify-center gap-1 rounded '
            f'bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-xs text-emerald-400 font-medium">'
            f'<i class="ti ti-check"></i> En bibliotheque</div>'
        )
        toast = (
            f'<div id="toast" hx-swap-oob="innerHTML">'
            f'<div class="rounded bg-emerald-600 px-3 py-2 text-sm text-white shadow-lg">{message}</div></div>'
        )
        return HTMLResponse(content=f"{badge}{toast}")
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@series_router.post("/series/{tmdb_id}/remove", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def series_remove(request: Request, tmdb_id: int):
    series_library = request.app.state.series_library
    series_library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/series_list.html", {"series": series_library.list()})


@series_router.get("/series/{tmdb_id}", response_class=HTMLResponse)
@series_router.get("/series/{tmdb_id}/detail", response_class=HTMLResponse)
async def series_detail(request: Request, tmdb_id: int):
    ctx = request.app.state.ctx
    series_library = request.app.state.series_library
    series = series_library.get(tmdb_id) if series_library else None

    # Fetch TMDB details & seasons
    tmdb_details = await ctx.tmdb.get_details("tv", tmdb_id)
    if series is None and tmdb_details is None:
        raise HTTPException(status_code=404, detail="Serie introuvable")

    title = series.title if series else (tmdb_details.title if tmdb_details else "")
    orig_from_lib = series.original_title if series else None
    orig_from_tmdb = tmdb_details.original_title if tmdb_details else None
    original_title = orig_from_lib or orig_from_tmdb
    year = (series.year if series else None) or (tmdb_details.year if tmdb_details else None)
    poster_path = (series.poster_path if series else None) or (tmdb_details.poster_path if tmdb_details else None)
    overview = tmdb_details.overview if tmdb_details else ""
    poster_url = f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None

    seasons_data = await ctx.tmdb.seasons(tmdb_id)

    # Jellyfin presence & episodes
    owned = await ctx.jellyfin.owned()
    jf_item_id = owned.get(f"tv:{tmdb_id}")
    jf_enabled = getattr(ctx.jellyfin, "enabled", False)
    if not jf_item_id and jf_enabled and hasattr(ctx.jellyfin, "find_matching"):
        match = await ctx.jellyfin.find_matching(title)
        if match and getattr(match, "media_type", None) == "tv":
            jf_item_id = match.id

    if jf_item_id and hasattr(ctx.jellyfin, "episodes"):
        jellyfin_episodes = await ctx.jellyfin.episodes(jf_item_id)
    else:
        jellyfin_episodes = set()

    grabbed_set = set(series.grabbed) if series else set()
    today = date.today().isoformat()

    enriched_seasons = []
    for s in seasons_data:
        s_tag = s.season_tag
        season_grabbed = s_tag in grabbed_set
        enriched_episodes = []
        for ep in s.episodes:
            in_jf = ep.code in jellyfin_episodes
            is_grabbed = ep.code in grabbed_set or season_grabbed
            is_unaired = bool(ep.air_date and ep.air_date > today)

            if in_jf:
                status = "jellyfin"
                label = "Dans Jellyfin"
                badge_class = "bg-green-500/15 text-green-300 border-green-500/20"
            elif is_grabbed:
                status = "grabbed"
                label = "Telecharge"
                badge_class = "bg-violet-500/15 text-violet-300 border-violet-500/20"
            elif is_unaired:
                status = "unaired"
                label = "A venir"
                badge_class = "bg-sky-500/15 text-sky-300 border-sky-500/20"
            else:
                status = "missing"
                label = "Manquant"
                badge_class = "bg-slate-700/40 text-slate-400 border-slate-700/50"

            enriched_episodes.append({
                "episode_number": ep.episode_number,
                "season_number": ep.season_number,
                "code": ep.code,
                "name": ep.name,
                "air_date": ep.air_date,
                "overview": ep.overview,
                "status": status,
                "status_label": label,
                "badge_class": badge_class,
                "in_jf": in_jf,
                "is_grabbed": is_grabbed,
                "search_query": f"{title} {ep.code}",
            })

        total_episodes = len(s.episodes)
        acquired_count = sum(1 for ep in enriched_episodes if ep["in_jf"] or ep["is_grabbed"])
        is_complete = acquired_count >= total_episodes and total_episodes > 0

        if is_complete:
            season_badge = "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
        elif acquired_count > 0:
            season_badge = "bg-amber-500/15 text-amber-300 border-amber-500/30"
        else:
            season_badge = "bg-slate-800 text-slate-400 border-slate-700"

        enriched_seasons.append({
            "season_number": s.season_number,
            "season_tag": s_tag,
            "name": s.name,
            "overview": s.overview,
            "poster_path": s.poster_path,
            "total_episodes": total_episodes,
            "acquired_count": acquired_count,
            "is_complete": is_complete,
            "badge_class": season_badge,
            "search_query": f"{title} {s_tag}",
            "episodes": enriched_episodes,
        })

    total_series_episodes = sum(s["total_episodes"] for s in enriched_seasons)
    total_series_acquired = sum(s["acquired_count"] for s in enriched_seasons)

    template_data = {
        "series": {
            "tmdb_id": tmdb_id,
            "title": title,
            "original_title": original_title,
            "year": year,
            "poster_path": poster_path,
            "poster_url": poster_url,
            "overview": overview,
            "in_library": series is not None,
            "grabbed": series.grabbed if series else [],
        },
        "seasons": enriched_seasons,
        "total_series_episodes": total_series_episodes,
        "total_series_acquired": total_series_acquired,
        "owned_jf": jf_item_id,
        "jellyfin_url": ctx.jellyfin.base_url,
    }

    is_modal = request.headers.get("HX-Request") == "true" or request.url.path.endswith("/detail")
    template_name = "partials/series_detail_modal.html" if is_modal else "series_detail.html"
    return templates.TemplateResponse(request, template_name, template_data)
