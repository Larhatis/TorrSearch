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


def _authenticate(request, username: str, password: str, auth: AuthSettings) -> str | None:
    """Return the role on success, else None.

    Prefers the multi-user store; falls back to the single env credential (treated as
    admin) when no store is wired or it is still empty.
    """
    users = getattr(request.app.state, "users", None)
    if users is not None and not users.is_empty():
        user = users.verify(username, password)
        return user.role.value if user else None
    if auth.check(username, password):
        return "admin"
    return None


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
    role = _authenticate(request, username, password, auth)
    if role is not None:
        request.session["user"] = username
        request.session["role"] = role
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
