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
    ctx = request.app.state.ctx
    if hasattr(ctx, "update_settings") and hasattr(ctx, "config") and not ctx.config.monitor.enabled:
        from torsearch.settings.mutations import set_monitor
        ctx.update_settings(set_monitor(ctx.config, ctx.config.monitor.model_copy(update={"enabled": True})))
    runner = getattr(request.app.state, "monitor", None)
    if runner is not None:
        runner.wake()

    target = request.headers.get("HX-Target", "")
    if target == "series-detail-view":
        return await _render_series_detail_response(
            request, tmdb_id, template_name="partials/series_detail_content.html"
        )
    message = "Serie suivie." if added else "Serie deja suivie."
    if target.startswith("media-action-") or target == "modal-action-wrapper":
        badge_id = target if target == "modal-action-wrapper" else f"media-action-tv-{tmdb_id}"
        badge = (
            f'<div id="{badge_id}" '
            f'class="mt-1.5 flex items-center justify-center gap-1 rounded '
            f'bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5 text-xs text-emerald-400 font-medium">'
            f'<i class="ti ti-check"></i> En surveillance</div>'
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
    if series_library:
        series_library.remove(tmdb_id)
    target = request.headers.get("HX-Target", "")
    if target == "series-detail-view":
        return await _render_series_detail_response(
            request, tmdb_id, template_name="partials/series_detail_content.html"
        )
    items = series_library.list() if series_library else []
    return templates.TemplateResponse(request, "partials/series_list.html", {"series": items})


async def _build_series_detail_data(request: Request, tmdb_id: int) -> dict:
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

    return {
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


async def _render_series_detail_response(
    request: Request, tmdb_id: int, template_name: str | None = None
) -> HTMLResponse:
    data = await _build_series_detail_data(request, tmdb_id)
    if template_name is None:
        target = request.headers.get("HX-Target", "")
        if target == "series-detail-view":
            template_name = "partials/series_detail_content.html"
        else:
            is_modal = request.headers.get("HX-Request") == "true" or request.url.path.endswith("/detail")
            template_name = "partials/series_detail_modal.html" if is_modal else "series_detail.html"
    return templates.TemplateResponse(request, template_name, data)


async def _ensure_series_in_library(request: Request, tmdb_id: int) -> WantedSeries:
    ctx = request.app.state.ctx
    series_library = request.app.state.series_library
    series = series_library.get(tmdb_id) if series_library else None
    if series is None:
        tmdb_details = await ctx.tmdb.get_details("tv", tmdb_id)
        series = WantedSeries(
            tmdb_id=tmdb_id,
            title=tmdb_details.title if tmdb_details else f"Serie {tmdb_id}",
            original_title=tmdb_details.original_title if tmdb_details else None,
            year=tmdb_details.year if tmdb_details else None,
            poster_path=tmdb_details.poster_path if tmdb_details else None,
            added_at=datetime.now(UTC),
        )
        if series_library:
            series_library.add(series)
    return series


@series_router.get("/series/{tmdb_id}", response_class=HTMLResponse)
@series_router.get("/series/{tmdb_id}/detail", response_class=HTMLResponse)
async def series_detail(request: Request, tmdb_id: int):
    return await _render_series_detail_response(request, tmdb_id)


@series_router.post(
    "/series/{tmdb_id}/season/{season_number}/toggle",
    response_class=HTMLResponse,
    dependencies=[Depends(require_member)],
)
async def series_toggle_season(request: Request, tmdb_id: int, season_number: int):
    ctx = request.app.state.ctx
    series_library = request.app.state.series_library
    series = await _ensure_series_in_library(request, tmdb_id)

    seasons_data = await ctx.tmdb.seasons(tmdb_id)
    target_season = next((s for s in seasons_data if s.season_number == season_number), None)
    if target_season is not None and series_library:
        s_tag = target_season.season_tag
        ep_codes = [ep.code for ep in target_season.episodes]
        all_keys = [s_tag] + ep_codes

        grabbed_set = set(series.grabbed)
        is_already_grabbed = (s_tag in grabbed_set) or (
            bool(ep_codes) and all(ep in grabbed_set for ep in ep_codes)
        )

        if is_already_grabbed:
            series_library.unmark_grabbed(tmdb_id, all_keys)
        else:
            series_library.mark_grabbed(tmdb_id, all_keys)

    return await _render_series_detail_response(request, tmdb_id, template_name="partials/series_detail_content.html")


@series_router.post(
    "/series/{tmdb_id}/episode/{code}/toggle",
    response_class=HTMLResponse,
    dependencies=[Depends(require_member)],
)
async def series_toggle_episode(request: Request, tmdb_id: int, code: str):
    series_library = request.app.state.series_library
    series = await _ensure_series_in_library(request, tmdb_id)

    code = code.upper().strip()
    grabbed_set = set(series.grabbed)
    s_tag = code[:3] if len(code) >= 3 and code.startswith("S") else None

    if series_library:
        if code in grabbed_set or (s_tag and s_tag in grabbed_set):
            to_remove = [code]
            if s_tag and s_tag in grabbed_set:
                to_remove.append(s_tag)
                # Keep other episodes in this season marked
                ctx = request.app.state.ctx
                seasons_data = await ctx.tmdb.seasons(tmdb_id)
                try:
                    s_num = int(s_tag[1:])
                    target_season = next((s for s in seasons_data if s.season_number == s_num), None)
                    if target_season:
                        other_eps = [ep.code for ep in target_season.episodes if ep.code != code]
                        if other_eps:
                            series_library.mark_grabbed(tmdb_id, other_eps)
                except Exception:
                    pass
            series_library.unmark_grabbed(tmdb_id, to_remove)
        else:
            series_library.mark_grabbed(tmdb_id, [code])

    return await _render_series_detail_response(request, tmdb_id, template_name="partials/series_detail_content.html")


@series_router.post(
    "/series/{tmdb_id}/mark-all",
    response_class=HTMLResponse,
    dependencies=[Depends(require_member)],
)
async def series_mark_all(request: Request, tmdb_id: int):
    ctx = request.app.state.ctx
    series_library = request.app.state.series_library
    await _ensure_series_in_library(request, tmdb_id)

    seasons_data = await ctx.tmdb.seasons(tmdb_id)
    all_keys: list[str] = []
    for s in seasons_data:
        all_keys.append(s.season_tag)
        all_keys.extend([ep.code for ep in s.episodes])

    if all_keys and series_library:
        series_library.mark_grabbed(tmdb_id, all_keys)

    return await _render_series_detail_response(request, tmdb_id, template_name="partials/series_detail_content.html")


@series_router.post(
    "/series/{tmdb_id}/unmark-all",
    response_class=HTMLResponse,
    dependencies=[Depends(require_member)],
)
async def series_unmark_all(request: Request, tmdb_id: int):
    series_library = request.app.state.series_library
    series = series_library.get(tmdb_id) if series_library else None
    if series and series.grabbed and series_library:
        series_library.unmark_grabbed(tmdb_id, list(series.grabbed))

    return await _render_series_detail_response(request, tmdb_id, template_name="partials/series_detail_content.html")
