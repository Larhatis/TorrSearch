from __future__ import annotations

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


_PUBLIC_PATHS = {"/login", "/logout"}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: AuthSettings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        if not self.settings.enabled or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        if request.session.get("user"):
            return await call_next(request)
        if request.headers.get("HX-Request") == "true":
            resp = Response(status_code=401)
            resp.headers["HX-Redirect"] = "/login"
            return resp
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
