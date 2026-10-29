from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from torsearch.web.auth import AuthSettings, session_fingerprint
from torsearch.web.templating import templates

auth_router = APIRouter()


def _safe_next(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "?"


def _authenticate(request, username: str, password: str, auth: AuthSettings) -> tuple[str, str] | None:
    """Return ``(role, session fingerprint)`` on success, else None.

    Prefers the multi-user store; falls back to the single env credential (treated as
    admin, no fingerprint) when no store is wired or it is still empty.
    """
    users = getattr(request.app.state, "users", None)
    if users is not None and not users.is_empty():
        user = users.verify(username, password)
        if user is None:
            return None
        return user.role.value, session_fingerprint(user.password_hash, auth.secret_key)
    if auth.check(username, password):
        return "admin", ""
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
    throttle = getattr(request.app.state, "login_throttle", None)
    key = _client_key(request)
    if throttle is not None and throttle.is_blocked(key):
        return templates.TemplateResponse(
            request, "login.html",
            {"next": _safe_next(next),
             "error": "Trop de tentatives. Reessaie dans quelques minutes."},
            status_code=429,
        )
    result = _authenticate(request, username, password, auth)
    if result is not None:
        role, fingerprint = result
        if throttle is not None:
            throttle.reset(key)
        request.session["user"] = username
        request.session["role"] = role
        request.session["pwd"] = fingerprint
        target = _safe_next(next)
        if role == "guest" and target == "/":
            target = "/discover"  # guests can't use the search home
        return RedirectResponse(target, status_code=303)
    if throttle is not None:
        throttle.record_failure(key)
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


_MIN_PASSWORD = 8


def _account(request: Request, error: str | None = None, notice: str | None = None,
             status_code: int = 200):
    username = request.session.get("user", "")
    users = getattr(request.app.state, "users", None)
    managed = users is not None and users.get(username) is not None
    return templates.TemplateResponse(
        request, "account.html",
        {"username": username, "managed": managed, "error": error, "notice": notice},
        status_code=status_code,
    )


@auth_router.get("/account")
async def account_page(request: Request):
    if not request.app.state.auth.enabled:
        return RedirectResponse("/", status_code=303)
    return _account(request)


@auth_router.post("/account/password")
async def account_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    auth: AuthSettings = request.app.state.auth
    if not auth.enabled:
        return RedirectResponse("/", status_code=303)
    username = request.session.get("user", "")
    users = getattr(request.app.state, "users", None)
    if users is None or users.get(username) is None:
        return _account(request, error="Ce compte est defini par les variables d'environnement.")
    throttle = getattr(request.app.state, "login_throttle", None)
    key = f"password:{username}"
    if throttle is not None and throttle.is_blocked(key):
        return _account(request, error="Trop de tentatives. Reessaie dans quelques minutes.",
                        status_code=429)
    if users.verify(username, current_password) is None:
        if throttle is not None:
            throttle.record_failure(key)
        return _account(request, error="Mot de passe actuel incorrect.")
    if len(new_password) < _MIN_PASSWORD:
        return _account(request, error=f"Le nouveau mot de passe doit faire au moins {_MIN_PASSWORD} caracteres.")
    if new_password != confirm_password:
        return _account(request, error="Les deux mots de passe ne correspondent pas.")
    users.set_password(username, new_password)
    if throttle is not None:
        throttle.reset(key)
    user = users.get(username)
    # Other sessions of this account are revoked (old fingerprint); this one is renewed.
    request.session["pwd"] = session_fingerprint(user.password_hash, auth.secret_key)
    return _account(request, notice="Mot de passe modifie. Tes autres sessions sont deconnectees.")
