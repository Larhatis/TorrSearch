from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from torsearch.library.calendar import build_calendar
from torsearch.web.authz import require_member
from torsearch.web.templating import templates

calendar_router = APIRouter()

_WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
           "septembre", "octobre", "novembre", "decembre"]


def day_label(day: date, today: date) -> str:
    delta = (day - today).days
    base = f"{_WEEKDAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}"
    if delta == 0:
        return f"Aujourd'hui · {base}"
    if delta == 1:
        return f"Demain · {base}"
    if delta == -1:
        return f"Hier · {base}"
    return base


@calendar_router.get("/calendar", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def calendar_page(request: Request):
    ctx = request.app.state.ctx
    library = getattr(request.app.state, "library", None)
    series_library = getattr(request.app.state, "series_library", None)
    today = date.today()
    tmdb = getattr(ctx, "tmdb", None)
    days = await build_calendar(
        tmdb,
        series_library.list() if series_library is not None else [],
        library.list() if library is not None else [],
        today,
    )
    return templates.TemplateResponse(request, "calendar.html", {
        "days": [(day, day_label(day, today), entries) for day, entries in days],
        "today": today,
        "tmdb_enabled": bool(tmdb and getattr(tmdb, "enabled", False)),
    })
