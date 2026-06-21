# Auth simple (identifiant + mot de passe) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protéger TorrSearch derrière un gate identifiant + mot de passe mono-utilisateur, activé via variables d'environnement, désactivé par défaut.

**Architecture:** `AuthSettings` (lecture d'env, comparaison constante, résolution de la clé de session) + `SessionMiddleware` (cookie signé Starlette) + `AuthMiddleware` (gate ASGI) + routeur `/login` `/logout` + page `login.html`. `create_app` câble le tout, désactivé sauf si `auth` explicite ; `main.build_app` lit l'environnement.

**Tech Stack:** Python 3.12+, FastAPI/Starlette, `itsdangerous` (requis par `SessionMiddleware`), Jinja2, Tailwind CDN, pytest + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-20-simple-auth-design.md`

---

## Structure des fichiers

- **Créer** `torsearch/web/auth.py` — `AuthSettings` (dataclass + `from_env` + `check`), `_load_or_create_secret`, `AuthMiddleware`.
- **Créer** `torsearch/web/auth_routes.py` — routeur `auth_router` (`GET /login`, `POST /login`, `POST /logout`), `_safe_next`.
- **Créer** `torsearch/web/templates/login.html` — page de connexion autonome.
- **Créer** `tests/test_auth.py` — tous les tests.
- **Modifier** `pyproject.toml` — ajout `itsdangerous>=2.0`.
- **Modifier** `torsearch/web/routes.py` — `create_app` accepte `auth`, pose `app.state.auth`, ajoute les middlewares, inclut `auth_router`.
- **Modifier** `torsearch/main.py` — `build_app` passe `AuthSettings.from_env()`.
- **Modifier** `torsearch/web/templating.py` — context processor `auth_enabled`.
- **Modifier** `torsearch/web/templates/base.html` — bouton « Deconnexion ».

---

## Task 1 : `AuthSettings` (lecture d'env, comparaison, clé)

**Files:**
- Create: `torsearch/web/auth.py`
- Modify: `pyproject.toml`
- Test: `tests/test_auth.py`

- [ ] **Step 1 : Ajouter la dépendance `itsdangerous`**

Dans `pyproject.toml`, dans `dependencies`, ajouter la ligne après `"defusedxml>=0.7",` :

```toml
    "itsdangerous>=2.0",
```

- [ ] **Step 2 : Écrire les tests `AuthSettings`**

Créer `tests/test_auth.py` :

```python
from torsearch.web.auth import AuthSettings


def test_disabled_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("TORSEARCH_USERNAME", raising=False)
    monkeypatch.delenv("TORSEARCH_PASSWORD", raising=False)
    auth = AuthSettings.from_env(data_dir="/tmp/does-not-matter")
    assert auth.enabled is False


def test_disabled_when_only_username(monkeypatch):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.delenv("TORSEARCH_PASSWORD", raising=False)
    assert AuthSettings.from_env(data_dir="/tmp").enabled is False


def test_enabled_and_check(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.delenv("TORSEARCH_SECRET_KEY", raising=False)
    auth = AuthSettings.from_env(data_dir=tmp_path)
    assert auth.enabled is True
    assert auth.check("admin", "s3cret") is True
    assert auth.check("admin", "wrong") is False
    assert auth.check("nope", "s3cret") is False


def test_secret_persisted_across_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.delenv("TORSEARCH_SECRET_KEY", raising=False)
    first = AuthSettings.from_env(data_dir=tmp_path).secret_key
    second = AuthSettings.from_env(data_dir=tmp_path).secret_key
    assert first and first == second
    assert (tmp_path / ".session_secret").exists()


def test_secret_from_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("TORSEARCH_USERNAME", "admin")
    monkeypatch.setenv("TORSEARCH_PASSWORD", "s3cret")
    monkeypatch.setenv("TORSEARCH_SECRET_KEY", "explicit-key")
    auth = AuthSettings.from_env(data_dir=tmp_path)
    assert auth.secret_key == "explicit-key"
    assert not (tmp_path / ".session_secret").exists()
```

- [ ] **Step 3 : Lancer les tests, vérifier l'échec**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.web.auth'`

- [ ] **Step 4 : Implémenter `AuthSettings`**

Créer `torsearch/web/auth.py` :

```python
from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


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
    def from_env(cls, data_dir: str | Path = "data") -> "AuthSettings":
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
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6 : Commit**

```bash
git add pyproject.toml torsearch/web/auth.py tests/test_auth.py
git commit -m "feat: add AuthSettings env-based credentials and session key"
```

---

## Task 2 : `AuthMiddleware` + câblage `create_app`

**Files:**
- Modify: `torsearch/web/auth.py` (ajout `AuthMiddleware`)
- Modify: `torsearch/web/routes.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1 : Écrire les tests du gate**

Ajouter en haut de `tests/test_auth.py` (après l'import existant) :

```python
from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.web.routes import create_app


class _FakeSearch:
    indexers: list = []

    async def search(self, query, category):
        return []


class _FakeContext:
    def __init__(self):
        self.search_service = _FakeSearch()
        self.transmission = None
        self.config = Config()


def _client(auth: AuthSettings) -> TestClient:
    return TestClient(create_app(_FakeContext(), auth=auth))


_ENABLED = AuthSettings(
    enabled=True, username="admin", password="s3cret", secret_key="test-key"
)
```

Puis ajouter les tests :

```python
def test_disabled_auth_allows_access():
    client = _client(AuthSettings(enabled=False))
    resp = client.get("/")
    assert resp.status_code == 200


def test_protected_route_redirects_to_login():
    client = _client(_ENABLED)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_htmx_request_gets_hx_redirect():
    client = _client(_ENABLED)
    resp = client.get(
        "/search", params={"q": "x"}, headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"] == "/login"
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `pytest tests/test_auth.py -v -k "redirect or htmx or disabled_auth"`
Expected: FAIL — `create_app() got an unexpected keyword argument 'auth'`

- [ ] **Step 3 : Ajouter `AuthMiddleware` dans `torsearch/web/auth.py`**

Ajouter ces imports en tête de `torsearch/web/auth.py` :

```python
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
```

Ajouter à la fin du fichier :

```python
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
```

- [ ] **Step 4 : Câbler `create_app` dans `torsearch/web/routes.py`**

Remplacer les imports en tête (ajouter après `from torsearch.context import AppContext`) :

```python
from starlette.middleware.sessions import SessionMiddleware

from torsearch.web.auth import AuthMiddleware, AuthSettings
```

Remplacer la signature et le corps de `create_app` :

```python
def create_app(ctx: AppContext, history=None, monitor=None, auth: AuthSettings | None = None) -> FastAPI:
    if auth is None:
        auth = AuthSettings(enabled=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if monitor is not None:
            await monitor.start()
        try:
            yield
        finally:
            if monitor is not None:
                await monitor.stop()

    app = FastAPI(title="TorrSearch", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.history = history
    app.state.auth = auth
    if auth.enabled:
        app.add_middleware(AuthMiddleware, settings=auth)
        app.add_middleware(
            SessionMiddleware,
            secret_key=auth.secret_key,
            https_only=auth.https_only,
            same_site="lax",
            max_age=60 * 60 * 24 * 14,
        )
    app.include_router(router)
    app.include_router(settings_router)
    app.include_router(downloads_router)
    app.include_router(surveillance_router)
    return app
```

Note : `AuthMiddleware` est ajouté **avant** `SessionMiddleware` pour que `SessionMiddleware` soit le plus externe (il peuple `request.session` que `AuthMiddleware` lit ensuite). `auth_router` sera inclus en Task 3.

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `pytest tests/test_auth.py -v -k "redirect or htmx or disabled_auth"`
Expected: PASS (3 tests)

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/auth.py torsearch/web/routes.py tests/test_auth.py
git commit -m "feat: gate all routes behind AuthMiddleware when auth enabled"
```

---

## Task 3 : Routes `/login` `/logout` + page `login.html`

**Files:**
- Create: `torsearch/web/auth_routes.py`
- Create: `torsearch/web/templates/login.html`
- Modify: `torsearch/web/routes.py` (inclure `auth_router`)
- Test: `tests/test_auth.py`

- [ ] **Step 1 : Écrire les tests du flux login/logout**

Ajouter à `tests/test_auth.py` :

```python
def test_login_page_accessible_without_session():
    client = _client(_ENABLED)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text
    assert 'name="username"' in resp.text


def test_login_success_then_access():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_login_failure_is_401_and_stays_locked():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "nope", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "incorrect" in resp.text.lower()
    assert client.get("/", follow_redirects=False).status_code == 303


def test_logout_clears_session():
    client = _client(_ENABLED)
    client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_login_rejects_open_redirect():
    client = _client(_ENABLED)
    resp = client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "//evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `pytest tests/test_auth.py -v -k "login or logout"`
Expected: FAIL — `GET /login` renvoie 303 (route absente, interceptée) ou 404

- [ ] **Step 3 : Créer `torsearch/web/auth_routes.py`**

```python
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
```

- [ ] **Step 4 : Créer `torsearch/web/templates/login.html`**

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Connexion — TorrSearch</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center">
  <main class="w-full max-w-sm px-6">
    <h1 class="text-2xl font-bold text-emerald-400 mb-6 text-center">TorrSearch</h1>
    {% if error %}
    <p class="mb-4 rounded border border-red-500/40 bg-red-500/20 px-3 py-2 text-sm text-red-200">{{ error }}</p>
    {% endif %}
    <form method="post" action="/login" class="space-y-4">
      <input type="hidden" name="next" value="{{ next }}">
      <div>
        <label class="mb-1 block text-sm text-slate-300" for="username">Identifiant</label>
        <input id="username" name="username" type="text" autocomplete="username" autofocus
               class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-400 focus:outline-none">
      </div>
      <div>
        <label class="mb-1 block text-sm text-slate-300" for="password">Mot de passe</label>
        <input id="password" name="password" type="password" autocomplete="current-password"
               class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 focus:border-emerald-400 focus:outline-none">
      </div>
      <button type="submit"
              class="w-full rounded bg-emerald-500 py-2 font-semibold text-slate-900 hover:bg-emerald-400">Se connecter</button>
    </form>
  </main>
</body>
</html>
```

- [ ] **Step 5 : Inclure `auth_router` dans `create_app`**

Dans `torsearch/web/routes.py`, ajouter l'import après les autres routeurs :

```python
from torsearch.web.auth_routes import auth_router
```

Et dans `create_app`, après `app.include_router(surveillance_router)`, ajouter :

```python
    app.include_router(auth_router)
```

- [ ] **Step 6 : Lancer les tests, vérifier le succès**

Run: `pytest tests/test_auth.py -v -k "login or logout"`
Expected: PASS (5 tests)

- [ ] **Step 7 : Commit**

```bash
git add torsearch/web/auth_routes.py torsearch/web/templates/login.html torsearch/web/routes.py tests/test_auth.py
git commit -m "feat: add login/logout routes and login page"
```

---

## Task 4 : Bouton « Deconnexion » + context processor

**Files:**
- Modify: `torsearch/web/templating.py`
- Modify: `torsearch/web/templates/base.html`
- Test: `tests/test_auth.py`

- [ ] **Step 1 : Écrire les tests du bouton de déconnexion**

Ajouter à `tests/test_auth.py` :

```python
def test_logout_button_shown_when_logged_in():
    client = _client(_ENABLED)
    client.post(
        "/login", data={"username": "admin", "password": "s3cret", "next": "/"},
        follow_redirects=False,
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Deconnexion" in resp.text
    assert 'action="/logout"' in resp.text


def test_logout_button_hidden_when_auth_disabled():
    client = _client(AuthSettings(enabled=False))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Deconnexion" not in resp.text
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `pytest tests/test_auth.py -v -k "logout_button"`
Expected: FAIL — `assert "Deconnexion" in resp.text` (bouton absent)

- [ ] **Step 3 : Ajouter le context processor dans `torsearch/web/templating.py`**

Remplacer le contenu de `torsearch/web/templating.py` par :

```python
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _auth_context(request):
    auth = getattr(request.app.state, "auth", None)
    return {"auth_enabled": bool(auth and getattr(auth, "enabled", False))}


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_auth_context])
```

- [ ] **Step 4 : Ajouter le bouton dans `torsearch/web/templates/base.html`**

Remplacer le bloc `<header>…</header>` (lignes 11-19) par :

```html
  <header class="border-b border-slate-700 px-6 py-4 flex items-center gap-6">
    <a href="/" class="text-xl font-bold text-emerald-400">TorrSearch</a>
    <nav class="flex gap-4 text-sm">
      <a href="/" class="hover:text-emerald-400">Recherche</a>
      <a href="/settings" class="hover:text-emerald-400">Reglages</a>
      <a href="/downloads" class="hover:text-emerald-400">Telechargements</a>
      <a href="/surveillance" class="hover:text-emerald-400">Surveillance</a>
    </nav>
    {% if auth_enabled %}
    <form method="post" action="/logout" class="ml-auto">
      <button type="submit" class="text-sm text-slate-400 hover:text-emerald-400">Deconnexion</button>
    </form>
    {% endif %}
  </header>
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `pytest tests/test_auth.py -v -k "logout_button"`
Expected: PASS (2 tests)

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/templating.py torsearch/web/templates/base.html tests/test_auth.py
git commit -m "feat: show logout button in nav when authenticated"
```

---

## Task 5 : Câbler l'environnement dans `main.build_app` + doc

**Files:**
- Modify: `torsearch/main.py`
- Modify: `.env.example`
- Test: `tests/test_main.py` (vérif non-régression)

- [ ] **Step 1 : Passer `AuthSettings.from_env()` dans `build_app`**

Dans `torsearch/main.py`, ajouter l'import :

```python
from torsearch.web.auth import AuthSettings
```

Dans `build_app`, remplacer la ligne `return create_app(ctx, history=history, monitor=monitor)` par :

```python
    return create_app(ctx, history=history, monitor=monitor, auth=AuthSettings.from_env())
```

- [ ] **Step 2 : Documenter les variables dans `.env.example`**

Ajouter à la fin de `.env.example` :

```dotenv
# Auth (optionnelle) : renseigner les deux pour activer le gate de connexion.
# Laisser vide pour un accès libre (ex. en local ou derrière un VPN).
TORSEARCH_USERNAME=
TORSEARCH_PASSWORD=
# Optionnel : clé de signature des sessions (sinon générée dans data/.session_secret).
TORSEARCH_SECRET_KEY=
# Mettre à 1 si TorrSearch est servi derrière HTTPS (cookie secure).
TORSEARCH_HTTPS=
```

- [ ] **Step 3 : Vérifier la non-régression de `test_main`**

Run: `pytest tests/test_main.py -v`
Expected: PASS (auth désactivée car `TORSEARCH_USERNAME`/`PASSWORD` non définis dans le test)

- [ ] **Step 4 : Commit**

```bash
git add torsearch/main.py .env.example
git commit -m "feat: read auth credentials from environment in build_app"
```

---

## Task 6 : Vérification finale

- [ ] **Step 1 : Lancer toute la suite**

Run: `pytest -q`
Expected: PASS — tous les tests existants (140) + les nouveaux tests de `tests/test_auth.py` verts, aucune régression.

- [ ] **Step 2 : Vérifier l'absence de gate par défaut (manuel, optionnel)**

Run: `TORSEARCH_USERNAME= TORSEARCH_PASSWORD= python -c "from torsearch.main import build_app; app = build_app(); print('auth.enabled =', app.state.auth.enabled)"`
Expected: `auth.enabled = False`

---

## Self-review (notes)

- **Couverture spec :** activation/désactivation (Task 1, Task 2), clé de session env/fichier (Task 1), `SessionMiddleware` + `AuthMiddleware` + ordre (Task 2), HTMX `HX-Redirect` (Task 2), routes login/logout + `next` validé (Task 3), `login.html` + bouton déconnexion conditionnel (Task 3/4), comparaison temps constant (Task 1), dépendance `itsdangerous` (Task 1), env dans `build_app` + `.env.example` (Task 5). ✔
- **Cohérence des noms :** `AuthSettings.check`, `app.state.auth`, session clé `"user"`, `auth_enabled` (template), `_safe_next` — identiques entre tasks. ✔
- **Pas de placeholder :** chaque step contient le code/commande exact. ✔
