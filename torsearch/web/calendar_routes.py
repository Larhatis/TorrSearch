from __future__ import annotations

import hmac
import secrets
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from torsearch.library.calendar import build_calendar, build_ics
from torsearch.web.authz import effective_role, require_admin, require_member
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


_TOKEN_DOC = "calendar_feed"


def _stored_token(request: Request) -> str | None:
    db = getattr(request.app.state, "db", None)
    if db is None:
        return getattr(request.app.state, "calendar_token", None)
    data = db.collection("app_secrets").get(_TOKEN_DOC)
    return data.get("token") if data else None


def _feed_token(request: Request, regenerate: bool = False) -> str:
    """Secret of the iCal feed URL (phone calendars cannot log in), kept in the database."""
    db = getattr(request.app.state, "db", None)
    store = db.collection("app_secrets") if db is not None else None
    if not regenerate:
        if store is not None:
            data = store.get(_TOKEN_DOC)
            if data and data.get("token"):
                return data["token"]
        elif getattr(request.app.state, "calendar_token", None):
            return request.app.state.calendar_token
    token = secrets.token_urlsafe(24)
    if store is not None:
        store.upsert(_TOKEN_DOC, {"token": token})
    else:
        request.app.state.calendar_token = token
    return token


def _public_url(request: Request, url) -> str:
    """The feed URL as the phone must reach it: behind an HTTPS reverse proxy uvicorn sees
    plain http, which would send the token in clear at every calendar sync. Only this
    displayed link trusts X-Forwarded-Proto (it is shown back to the admin who asked)."""
    text = str(url)
    if request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https":
        text = "https://" + text.split("://", 1)[1]
    return text


async def _days(request: Request, today: date, past_days: int = 7, future_days: int = 60):
    ctx = request.app.state.ctx
    library = getattr(request.app.state, "library", None)
    series_library = getattr(request.app.state, "series_library", None)
    return await build_calendar(
        getattr(ctx, "tmdb", None),
        series_library.list() if series_library is not None else [],
        library.list() if library is not None else [],
        today, past_days=past_days, future_days=future_days,
    )


@calendar_router.get("/calendar", response_class=HTMLResponse, dependencies=[Depends(require_member)])
async def calendar_page(request: Request):
    ctx = request.app.state.ctx
    today = date.today()
    tmdb = getattr(ctx, "tmdb", None)
    days = await _days(request, today)
    feed_url = webcal_url = None
    if effective_role(request) == "admin":
        # Admin only: a link shown to members would outlive a demoted or deleted account.
        feed_url = _public_url(request, request.url_for("calendar_feed").include_query_params(
            token=_feed_token(request)))
        webcal_url = "webcal://" + feed_url.split("://", 1)[1]
    return templates.TemplateResponse(request, "calendar.html", {
        "days": [(day, day_label(day, today), entries) for day, entries in days],
        "today": today,
        "tmdb_enabled": bool(tmdb and getattr(tmdb, "enabled", False)),
        "feed_url": feed_url,
        "webcal_url": webcal_url,
    })


@calendar_router.get("/calendar.ics", name="calendar_feed")
async def calendar_feed(request: Request, token: str = ""):
    """Public route (listed in the auth middleware) protected by the feed token."""
    expected = _stored_token(request)  # never created by an anonymous request
    if not token or not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        return Response("Introuvable", status_code=404)
    days = await _days(request, date.today(), past_days=30, future_days=120)
    return Response(
        build_ics(days),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="torrsearch.ics"'},
    )


@calendar_router.post("/calendar/token", dependencies=[Depends(require_admin)])
async def regenerate_token(request: Request):
    """New feed URL: every phone subscribed with the old one stops receiving updates."""
    _feed_token(request, regenerate=True)
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/calendar"})
    return RedirectResponse("/calendar", status_code=303)
