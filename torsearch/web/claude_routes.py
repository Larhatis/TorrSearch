from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from torsearch.users.store import Role, role_at_least
from torsearch.web.templating import templates

claude_router = APIRouter()


def _provider(request: Request):
    provider = getattr(request.app.state, "claude_provider", None)
    if provider is None:
        raise HTTPException(status_code=404)
    return provider


def _page(request: Request, demande: str, client_name: str | None, error: str | None = None, status: int = 200):
    return templates.TemplateResponse(
        request, "claude_consent.html", {"demande": demande, "client_name": client_name, "error": error},
        status_code=status,
    )


@claude_router.get("/claude/autoriser", response_class=HTMLResponse)
async def consent_page(request: Request, demande: str = ""):
    pending = _provider(request).pending(demande)
    if pending is None:
        return _page(request, demande, None, "Demande expiree : relance la connexion depuis Claude.", 400)
    return _page(request, demande, pending.client_name)


@claude_router.post("/claude/autoriser", response_class=HTMLResponse)
async def consent_submit(request: Request, demande: str = Form(""), username: str = Form(""),
                         password: str = Form(""), decision: str = Form("")):
    """Public page (reached from claude.ai): an admin logs in here to grant Claude access."""
    provider = _provider(request)
    pending = provider.pending(demande)
    if pending is None:
        return _page(request, demande, None, "Demande expiree : relance la connexion depuis Claude.", 400)
    if decision == "refuser":
        return RedirectResponse(provider.deny(demande), status_code=303)
    throttle = request.app.state.login_throttle
    key = f"claude:{request.client.host if request.client else '?'}"
    if throttle.is_blocked(key):
        return _page(request, demande, pending.client_name, "Trop de tentatives : reessaie dans 15 minutes.", 429)
    users = getattr(request.app.state, "users", None)
    user = users.verify(username, password) if users is not None else None
    if user is None:
        throttle.record_failure(key)
        return _page(request, demande, pending.client_name, "Identifiant ou mot de passe incorrect.", 401)
    if not role_at_least(user.role, Role.ADMIN):
        return _page(request, demande, pending.client_name, "Seul un administrateur peut autoriser Claude.", 403)
    throttle.reset(key)
    return RedirectResponse(provider.approve(demande, user.username), status_code=303)
