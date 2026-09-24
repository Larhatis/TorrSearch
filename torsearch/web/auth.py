from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

_TRUE = {"1", "true", "yes", "on"}


class LoginThrottle:
    """In-memory sliding-window throttle: blocks a key after too many failures."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 900.0, clock=time.monotonic):
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = self._clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self._window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def is_blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self._max

    def record_failure(self, key: str) -> None:
        self._failures.setdefault(key, []).append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


def _load_or_create_secret(path: Path) -> str:
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool = False
    username: str = ""
    password: str = ""
    secret_key: str = ""
    https_only: bool = False

    @classmethod
    def from_env(cls, data_dir: str | Path = "data") -> AuthSettings:
        username = os.environ.get("TORSEARCH_USERNAME", "").strip()
        password = os.environ.get("TORSEARCH_PASSWORD", "")
        if not username or not password:
            return cls(enabled=False)
        secret_key = os.environ.get("TORSEARCH_SECRET_KEY", "").strip()
        if not secret_key:
            secret_key = _load_or_create_secret(Path(data_dir) / ".session_secret")
        https_only = os.environ.get("TORSEARCH_HTTPS", "").strip().lower() in _TRUE
        return cls(
            enabled=True,
            username=username,
            password=password,
            secret_key=secret_key,
            https_only=https_only,
        )

    def check(self, username: str, password: str) -> bool:
        if not self.enabled:
            return False
        user_ok = hmac.compare_digest(username.encode(), self.username.encode())
        pass_ok = hmac.compare_digest(password.encode(), self.password.encode())
        return user_ok and pass_ok


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Sane default security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_TRUSTED_FETCH_SITES = {"same-origin", "none"}


class CrossSiteGuardMiddleware(BaseHTTPMiddleware):
    """Refuse state-changing requests the browser flags as coming from another site.

    CSRF protection without tokens, via Fetch Metadata: modern browsers always send
    ``Sec-Fetch-Site``, so a forged cross-site form is rejected even when auth is
    disabled. Clients that don't send the header (curl, scripts) are let through.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method not in _SAFE_METHODS:
            site = request.headers.get("sec-fetch-site")
            if site and site not in _TRUSTED_FETCH_SITES:
                return Response("Requete inter-sites refusee.", status_code=403)
        return await call_next(request)


_PUBLIC_PATHS = {"/login", "/logout"}
_PUBLIC_PREFIXES = ("/static/",)


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


def _route_path(request: Request) -> str:
    """The path the router matches, from the ASGI scope (never from the Host header)."""
    path = request.scope["path"]
    root = request.scope.get("root_path", "")
    return path[len(root):] if root and path.startswith(root) else path


def session_fingerprint(password_hash: str, secret_key: str) -> str:
    """Short HMAC of the password hash, stored in the session at login.

    Re-creating an account (or changing its password) changes the hash, which revokes every
    session issued before.
    """
    return hmac.new(secret_key.encode(), password_hash.encode(), hashlib.sha256).hexdigest()[:16]


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: AuthSettings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        if not self.settings.enabled or _is_public(_route_path(request)):
            return await call_next(request)
        username = request.session.get("user")
        if username:
            users = getattr(request.app.state, "users", None)
            user = users.get(username) if users is not None else None
            if user is not None:
                fingerprint = session_fingerprint(user.password_hash, self.settings.secret_key)
                if hmac.compare_digest(request.session.get("pwd", ""), fingerprint):
                    # Authorization uses the role stored in the DB, not the one frozen in
                    # the cookie at login: demotions and promotions apply on the next request.
                    request.state.role = user.role.value
                    return await call_next(request)
            elif (users is None or users.is_empty()) and username == self.settings.username:
                # Single-credential mode (no user store yet): only the env admin can log in.
                return await call_next(request)
            # Account deleted or re-created since login: drop the stale session.
            request.session.clear()
        return _unauthenticated(request)


def _unauthenticated(request: Request) -> Response:
    if request.headers.get("HX-Request") == "true":
        resp = Response(status_code=401)
        resp.headers["HX-Redirect"] = "/login"
        return resp
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
