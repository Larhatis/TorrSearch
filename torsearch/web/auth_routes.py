from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from torsearch.web.auth import AuthSettings
from torsearch.web.templating import templates

auth_router = APIRouter()


def _safe_next(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


@auth_router.get("/login")
async def login_form(request: Request, next: str = "/"):
    auth: AuthSettings = request.app.state.auth
    if not auth.enabled or request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"next": _safe_next(next), "error": None}
    )


@auth_router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    auth: AuthSettings = request.app.state.auth
    if not auth.enabled:
        return RedirectResponse("/", status_code=303)
    if auth.check(username, password):
        request.session["user"] = username
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": _safe_next(next), "error": "Identifiant ou mot de passe incorrect."},
        status_code=401,
    )


@auth_router.post("/logout")
async def logout(request: Request):
    if request.app.state.auth.enabled:
        request.session.clear()
    return RedirectResponse("/login", status_code=303)
