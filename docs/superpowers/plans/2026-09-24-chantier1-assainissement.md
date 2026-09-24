# Chantier 1 — Assainissement sécurité & fiabilité — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger les 10 défauts de sécurité et de fiabilité (D1 à D10) relevés à l'audit, sans changer le périmètre fonctionnel ni le modèle de données.

**Architecture:** Correctifs ciblés, un commit par défaut, chacun précédé d'un test rouge. Le middleware d'auth relit l'utilisateur en base ; les templates perdent tout JS inline au profit de `static/app.js` ; le client Transmission devient une façade async (threads) ; la page Réglages ne renvoie plus aucun secret ; la clé TMDB devient réglable avec repli sur l'environnement.

**Tech Stack:** Python 3.12+, FastAPI / Starlette, Jinja2 + HTMX, transmission-rpc, SQLite (document-store maison), pytest (+ pytest-asyncio en mode auto, respx).

**Spec :** `docs/superpowers/specs/2026-09-24-chantier1-assainissement-design.md`

**Commandes :** toujours via le venv du worktree : `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy` (pas `uv run`, qui resynchroniserait l'environnement). Un serveur de dev tourne peut-être déjà sur le port 8000 avec `--reload` : il recharge tout seul, ne pas le relancer.

**Conventions du dépôt :** docstrings et commentaires en anglais ; messages utilisateur en français (les templates HTML s'écrivent sans accents, comme l'existant) ; messages de commit `type(portée): description` en français ; chaque commit se termine par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## Structure des fichiers

- **Créer** `torsearch/web/forms.py` — helpers de lecture des champs de formulaire (D7).
- **Créer** `torsearch/web/static/app.js` — comportements front par délégation d'événements (D2).
- **Modifier** `torsearch/web/routes.py` — helpers communs (D7), montage `/static` (D2), `await` Transmission (D3).
- **Modifier** `torsearch/web/surveillance_routes.py` — helpers communs (D7), `regrab_hours` préservé (D6).
- **Modifier** `torsearch/web/settings_routes.py` — helper `to_int` (D7), secrets conservés si vides (D4), route `/settings/metadata` (D10).
- **Modifier** `torsearch/settings/mutations.py` — validation des noms (D8), `set_metadata` (D10).
- **Modifier** `torsearch/web/auth.py` — révocation des sessions (D1), préfixe public `/static/` (D2).
- **Modifier** `torsearch/web/authz.py` — rôle lu depuis `request.state` (D1).
- **Modifier** `torsearch/web/templating.py` — `STATIC_DIR` (D2).
- **Modifier** `torsearch/transmission/client.py` — façade async (D3).
- **Modifier** `torsearch/web/downloads_routes.py`, `torsearch/monitor/runner.py` — `await` Transmission (D3).
- **Modifier** `torsearch/context.py` — repli `TMDB_API_KEY` (D10).
- **Modifier** templates : `base.html`, `index.html`, `partials/results.html`, `partials/media_results.html`, `partials/library_list.html`, `partials/series_list.html` (D2) ; `settings.html`, `partials/indexer_row.html` (D4, D10) ; `discover.html` (D10).
- **Modifier** `pyproject.toml` (D9), `.env.example`, `docker-compose.yml`, `README.md` (D5).
- **Tests** : créer `tests/test_forms.py`, `tests/test_session_revocation.py`, `tests/test_no_inline_js.py` ; modifier `tests/test_surveillance_web.py`, `tests/test_settings_mutations.py`, `tests/test_web.py`, `tests/test_discover_web.py`, `tests/test_transmission.py`, `tests/test_monitor_runner.py`, `tests/test_downloads_web.py`, `tests/test_authz.py`, `tests/test_settings_web.py`, `tests/test_context.py`.

---

## Task 1 : Helpers de formulaire communs (D7)

**Files:**
- Create: `torsearch/web/forms.py`
- Modify: `torsearch/web/routes.py`, `torsearch/web/surveillance_routes.py`, `torsearch/web/settings_routes.py`
- Test: `tests/test_forms.py`

- [ ] **Step 1 : Écrire le test**

Créer `tests/test_forms.py` :

```python
from torsearch.web.forms import GB, split_words, to_int, to_size_bytes


def test_to_int_parses_and_falls_back():
    assert to_int("12") == 12
    assert to_int("-3") == -3
    assert to_int("abc") == 0
    assert to_int("", default=3) == 3


def test_to_size_bytes_converts_gb():
    assert to_size_bytes("1.5") == int(1.5 * GB)
    assert to_size_bytes("0") is None
    assert to_size_bytes("") is None
    assert to_size_bytes("xyz") is None


def test_split_words_on_spaces_and_commas():
    assert split_words("cam, ts  multi") == ["cam", "ts", "multi"]
    assert split_words("") == []
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_forms.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.web.forms'`

- [ ] **Step 3 : Créer le module**

Créer `torsearch/web/forms.py` :

```python
from __future__ import annotations

import re

GB = 1024 ** 3


def to_int(value: str, default: int = 0) -> int:
    """Integer from a form field; ``default`` when blank or invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_size_bytes(value_gb: str) -> int | None:
    """Size typed in GB -> bytes; ``None`` when blank, invalid or <= 0."""
    try:
        gb = float(value_gb)
    except (TypeError, ValueError):
        return None
    return int(gb * GB) if gb > 0 else None


def split_words(value: str) -> list[str]:
    """Words of a free-text field, split on spaces and commas."""
    return [w for w in re.split(r"[\s,]+", value) if w]
```

- [ ] **Step 4 : Vérifier que le test passe**

Run: `.venv/bin/pytest tests/test_forms.py -q`
Expected: `3 passed`

- [ ] **Step 5 : Brancher `routes.py`**

Dans `torsearch/web/routes.py` :
- supprimer la ligne `import re` ;
- ajouter l'import `from torsearch.web.forms import GB, split_words, to_int, to_size_bytes` entre `from torsearch.web.downloads_routes import downloads_router` et `from torsearch.web.library_routes import library_router` (ordre alphabétique exigé par ruff/isort) ;
- supprimer la constante `_GB = 1024 ** 3` et les fonctions `_to_int` et `_to_size_bytes` ;
- dans `_active_filters`, remplacer les deux `_GB` par `GB` ;
- dans `search`, remplacer la construction de `ResultFilters` par :

```python
    filters = ResultFilters(
        min_seeders=max(to_int(min_seeders), 0),
        min_size=to_size_bytes(min_size_gb),
        max_size=to_size_bytes(max_size_gb),
        qualities=[item for item in quality if item],
        exclude=split_words(exclude),
        sort=effective_sort,
        direction=effective_dir,
    )
```

- [ ] **Step 6 : Brancher `surveillance_routes.py`**

Dans `torsearch/web/surveillance_routes.py` :
- supprimer `import re`, la constante `_GB` et les fonctions `_to_int` et `_to_size_bytes` ;
- ajouter `from torsearch.web.forms import split_words, to_int, to_size_bytes` (avant `from torsearch.web.templating import templates`) ;
- dans `add_search`, remplacer la construction de `SavedSearch` par :

```python
        saved = SavedSearch(
            name=name, query=query, category=category, mode=mode,
            min_seeders=max(to_int(min_seeders), 0),
            min_size=to_size_bytes(min_size_gb),
            max_size=to_size_bytes(max_size_gb),
            qualities=[q for q in quality if q],
            exclude=split_words(exclude),
        )
```

- [ ] **Step 7 : Brancher `settings_routes.py`**

Dans `torsearch/web/settings_routes.py` :
- ajouter `from torsearch.web.forms import to_int` (avant `from torsearch.web.templating import templates`) ;
- dans `update_library`, remplacer
  `min_seeders=int(min_seeders) if min_seeders.lstrip("-").isdigit() else 0,`
  par `min_seeders=to_int(min_seeders),`.

- [ ] **Step 8 : Suite complète + lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests`
Expected: tous les tests passent ; `All checks passed!`

- [ ] **Step 9 : Commit**

```bash
git add torsearch/web/forms.py torsearch/web/routes.py torsearch/web/surveillance_routes.py torsearch/web/settings_routes.py tests/test_forms.py
git commit -m "refactor(web): helpers de formulaire communs (D7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 2 : Surveillance — préserver `regrab_hours` (D6)

**Files:**
- Modify: `torsearch/web/surveillance_routes.py` (`update_monitor`)
- Test: `tests/test_surveillance_web.py`

- [ ] **Step 1 : Écrire le test**

Ajouter à la fin de `tests/test_surveillance_web.py` :

```python
def test_update_monitor_preserves_regrab_hours(tmp_path):
    from torsearch.config import MonitorConfig

    client, ctx, _ = _client(tmp_path, Config(monitor=MonitorConfig(regrab_hours=72)))
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "15"})
    assert resp.status_code == 200
    assert ctx.config.monitor.regrab_hours == 72
    assert ctx.config.monitor.interval_minutes == 15
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_surveillance_web.py -q -k regrab`
Expected: FAIL — `assert 48 == 72`

- [ ] **Step 3 : Corriger `update_monitor`**

Dans `torsearch/web/surveillance_routes.py`, remplacer la fonction `update_monitor` par :

```python
@surveillance_router.post("/surveillance/monitor", response_class=HTMLResponse)
async def update_monitor(request: Request, enabled: str | None = Form(None), interval_minutes: str = Form("30")):
    ctx: AppContext = request.app.state.ctx
    try:
        # Rebuild from the current config (keeps regrab_hours) and validate the form values;
        # model_copy(update=...) would skip validation and store "30" as a string.
        monitor = MonitorConfig.model_validate({
            **ctx.config.monitor.model_dump(),
            "enabled": enabled is not None,
            "interval_minutes": interval_minutes,
        })
        ctx.update_settings(set_monitor(ctx.config, monitor))
        return _body(request, notice="Surveillance mise a jour.")
    except (ValidationError, SettingsError) as exc:
        return _body(request, error=f"Erreur : {exc}")
```

- [ ] **Step 4 : Vérifier**

Run: `.venv/bin/pytest tests/test_surveillance_web.py -q`
Expected: tous passent (dont `test_update_monitor_settings` qui vérifie `interval_minutes == 15`).

- [ ] **Step 5 : Commit**

```bash
git add torsearch/web/surveillance_routes.py tests/test_surveillance_web.py
git commit -m "fix(surveillance): ne plus réinitialiser regrab_hours (D6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 3 : Noms compatibles avec les URLs (D8)

**Files:**
- Modify: `torsearch/settings/mutations.py`
- Test: `tests/test_settings_mutations.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter à la fin de `tests/test_settings_mutations.py` :

```python
@pytest.mark.parametrize("bad", ["a/b", "quoi?", "x#1", "50%", "   ", ""])
def test_add_indexer_rejects_names_that_break_urls(bad):
    with pytest.raises(SettingsError):
        add_indexer(Config(), _ix(bad))


def test_update_indexer_validates_only_renames():
    cfg = Config(indexers=[_ix("old/name")])  # legacy config: still loads
    with pytest.raises(SettingsError):
        update_indexer(cfg, "old/name", _ix("new/name"))
    kept = update_indexer(cfg, "old/name", _ix("old/name", url="https://x/api"))
    assert kept.indexers[0].url == "https://x/api"


def test_saved_search_and_channel_names_are_validated():
    # Local imports, like the rest of this file (a module-level import would clash with them: F811).
    from torsearch.config import NotificationChannel, SavedSearch
    from torsearch.settings.mutations import add_channel, add_saved_search

    with pytest.raises(SettingsError):
        add_saved_search(Config(), SavedSearch(name="a/b", query="q"))
    with pytest.raises(SettingsError):
        add_channel(Config(), NotificationChannel(name="c?d", type="discord", url="https://x"))
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_settings_mutations.py -q`
Expected: FAIL — `Failed: DID NOT RAISE <class 'torsearch.settings.mutations.SettingsError'>` (plusieurs cas)

- [ ] **Step 3 : Implémenter la validation**

Dans `torsearch/settings/mutations.py`, ajouter juste après la classe `SettingsError` :

```python
_URL_BREAKING = set("/?#%")


def _check_name(name: str, what: str) -> None:
    """Names are used as URL path segments: refuse blanks and URL-breaking characters."""
    if not name.strip():
        raise SettingsError(f"Nom obligatoire ({what}).")
    bad = sorted(_URL_BREAKING & set(name))
    if bad:
        raise SettingsError(f"Nom invalide ({what}) : caractères interdits {' '.join(bad)}.")
```

Puis appeler la validation :
- en première ligne de `add_indexer` : `_check_name(indexer.name, "tracker")` ;
- dans `update_indexer`, remplacer
  ```python
      if indexer.name != name and _index_of(config, indexer.name) != -1:
          raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
  ```
  par
  ```python
      if indexer.name != name:
          _check_name(indexer.name, "tracker")
          if _index_of(config, indexer.name) != -1:
              raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
  ```
- en première ligne de `add_saved_search` : `_check_name(saved_search.name, "recherche")` ;
- en première ligne de `add_channel` : `_check_name(channel.name, "canal")`.

- [ ] **Step 4 : Vérifier**

Run: `.venv/bin/pytest -q`
Expected: tous passent (les tests web existants utilisent des noms valides).

- [ ] **Step 5 : Commit**

```bash
git add torsearch/settings/mutations.py tests/test_settings_mutations.py
git commit -m "fix(settings): refuser les noms qui cassent les URLs (D8)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 4 : Révocation des sessions (D1)

**Files:**
- Modify: `torsearch/web/auth.py` (`AuthMiddleware`)
- Modify: `torsearch/web/authz.py` (`effective_role`)
- Test: `tests/test_session_revocation.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_session_revocation.py` :

```python
from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.db.database import Database
from torsearch.search.service import SearchService
from torsearch.users.store import Role, UserStore
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app


class _Ctx:
    def __init__(self):
        self.search_service = SearchService([])
        self.transmission = None
        self.config = Config()


def _setup(tmp_path):
    store = UserStore(Database(tmp_path / "t.db").collection("users"))
    store.add("admin", "pw", Role.ADMIN)
    store.add("bob", "pw", Role.MEMBER)
    app = create_app(_Ctx(), auth=AuthSettings(enabled=True, secret_key="k"), users=store)
    return TestClient(app), store


def _login(client, username):
    resp = client.post("/login", data={"username": username, "password": "pw", "next": "/"},
                       follow_redirects=False)
    assert resp.status_code == 303


def test_deleted_user_session_is_revoked(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    assert client.get("/search", params={"q": ""}).status_code == 200
    store.remove("bob")
    resp = client.get("/search", params={"q": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    # the stale session was cleared: still logged out on the next request
    assert client.get("/", follow_redirects=False).status_code == 303


def test_deleted_user_htmx_request_gets_hx_redirect(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.remove("bob")
    resp = client.get("/search", params={"q": "x"}, headers={"HX-Request": "true"},
                      follow_redirects=False)
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"] == "/login"


def test_demoted_user_loses_rights_immediately(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "bob")
    store.set_role("bob", Role.GUEST)
    assert client.get("/search", params={"q": ""}).status_code == 403


def test_promoted_user_gains_rights_without_relogin(tmp_path):
    client, store = _setup(tmp_path)
    store.set_role("bob", Role.GUEST)
    _login(client, "bob")
    assert client.get("/search", params={"q": ""}).status_code == 403
    store.set_role("bob", Role.MEMBER)
    assert client.get("/search", params={"q": ""}).status_code == 200


def test_nav_reflects_role_from_store(tmp_path):
    client, store = _setup(tmp_path)
    _login(client, "admin")
    assert "ti-settings" in client.get("/").text  # admin-only nav entry
    store.add("admin2", "pw", Role.ADMIN)  # keep an admin: the last one can't be demoted
    store.set_role("admin", Role.MEMBER)
    assert "ti-settings" not in client.get("/").text
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_session_revocation.py -q`
Expected: 5 FAIL — suppression : `assert 200 == 303` ; HTMX : `assert 200 == 401` ; rétrogradation : `assert 200 == 403` ; promotion : `assert 403 == 200` ; nav : `assert 'ti-settings' not in ...`.

- [ ] **Step 3 : Implémenter dans `auth.py`**

Dans `torsearch/web/auth.py`, remplacer la classe `AuthMiddleware` (tout ce qui suit `_PUBLIC_PATHS = {"/login", "/logout"}`) par :

```python
class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: AuthSettings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        if not self.settings.enabled or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        username = request.session.get("user")
        if username:
            users = getattr(request.app.state, "users", None)
            user = users.get(username) if users is not None else None
            if user is not None:
                # Authorization uses the role stored in the DB, not the one frozen in the
                # cookie at login: demotions and promotions apply on the next request.
                request.state.role = user.role.value
                return await call_next(request)
            if users is None or users.is_empty():
                # Single-credential mode (no user store yet): the session is the truth.
                return await call_next(request)
            # The account was deleted after login: drop the stale session.
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
```

- [ ] **Step 4 : Implémenter dans `authz.py`**

Dans `torsearch/web/authz.py`, remplacer `effective_role` par :

```python
def effective_role(request: Request) -> str:
    """Role driving authorization. Auth disabled => everyone is admin (open app)."""
    auth = getattr(request.app.state, "auth", None)
    if not (auth and getattr(auth, "enabled", False)):
        return Role.ADMIN.value
    role = getattr(request.state, "role", None)  # set by AuthMiddleware from the user store
    if role:
        return role
    try:
        return request.session.get("role") or Role.GUEST.value
    except (AssertionError, AttributeError):
        return Role.GUEST.value
```

- [ ] **Step 5 : Vérifier**

Run: `.venv/bin/pytest tests/test_session_revocation.py tests/test_auth.py tests/test_authz.py tests/test_users_web.py tests/test_requests_web.py -q && .venv/bin/pytest -q`
Expected: tout passe (le mode identifiant unique de `test_auth.py`, sans store, est inchangé).

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/auth.py torsearch/web/authz.py tests/test_session_revocation.py
git commit -m "fix(auth): révoquer la session d'un compte supprimé, rôle lu en base (D1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 5 : Fin du JS inline — `static/app.js` (D2)

**Files:**
- Create: `torsearch/web/static/app.js`
- Modify: `torsearch/web/templating.py`, `torsearch/web/routes.py`, `torsearch/web/auth.py`
- Modify: `torsearch/web/templates/base.html`, `index.html`, `partials/results.html`, `partials/media_results.html`, `partials/library_list.html`, `partials/series_list.html`
- Test: create `tests/test_no_inline_js.py` ; modify `tests/test_web.py`, `tests/test_discover_web.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_no_inline_js.py` :

```python
import re

from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService
from torsearch.web.auth import AuthSettings
from torsearch.web.routes import create_app
from torsearch.web.templating import TEMPLATES_DIR

_INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


class _Indexer:
    name = "t1"
    enabled = True

    def __init__(self, results):
        self._results = results

    async def search(self, query, category):
        return list(self._results)


class _Ctx:
    def __init__(self, results):
        self.search_service = SearchService([_Indexer(results)])
        self.transmission = None
        self.config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")])


def _result(download_url="magnet:?x"):
    return SearchResult(title="Film.1080p", size=1, seeders=5, leechers=0, source="t1",
                        category=Category.MOVIES, download_url=download_url)


def test_templates_have_no_inline_event_handlers():
    offenders = [
        f"{path.relative_to(TEMPLATES_DIR)}: {m.group(0).strip()}"
        for path in sorted(TEMPLATES_DIR.rglob("*.html"))
        for m in _INLINE_HANDLER.finditer(path.read_text())
    ]
    assert offenders == []


def test_download_url_lands_escaped_in_data_attribute():
    evil = "magnet:?xt=urn:btih:X');alert(document.domain)//"
    html = TestClient(create_app(_Ctx([_result(evil)]))).get("/search", params={"q": "film"}).text
    assert "onclick" not in html
    assert 'data-copy="magnet:?xt=urn:btih:X&#39;);alert(document.domain)//"' in html


def test_filter_chip_value_is_data_not_code():
    html = TestClient(create_app(_Ctx([_result()]))).get(
        "/search", params={"q": "film", "quality": ["1080p", "');alert(1)//"]}
    ).text
    assert "onclick" not in html
    assert 'data-value="&#39;);alert(1)//"' in html


def test_app_js_served_without_session():
    client = TestClient(create_app(_Ctx([]), auth=AuthSettings(enabled=True, secret_key="k")))
    resp = client.get("/static/app.js", follow_redirects=False)
    assert resp.status_code == 200
    assert "function clearFilter" in resp.text


def test_base_layout_loads_app_js():
    html = TestClient(create_app(_Ctx([]))).get("/").text
    assert '<script src="/static/app.js" defer></script>' in html
```

Dans `tests/test_web.py`, remplacer `test_index_defines_clear_filter_helper` par :

```python
def test_index_loads_clear_filter_helper():
    client, _ = _make()
    assert '<script src="/static/app.js" defer></script>' in client.get("/").text
    assert "function clearFilter" in client.get("/static/app.js").text
```

et, dans `test_search_renders_active_filter_chip`, remplacer la ligne
`assert "clearFilter('min_seeders')" in resp.text` par `assert "onclick" not in resp.text`.

Dans `tests/test_discover_web.py`, remplacer `test_discover_poster_has_onerror_fallback` par :

```python
def test_discover_poster_has_fallback_hook():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert "data-poster" in resp.text
    assert "onerror" not in resp.text
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_no_inline_js.py tests/test_web.py tests/test_discover_web.py -q`
Expected: FAIL — `test_templates_have_no_inline_event_handlers` liste 5 attributs (`onclick` ×2, `onerror` ×3) ; `/static/app.js` renvoie 404 ; etc.

- [ ] **Step 3 : Créer `app.js`**

Créer `torsearch/web/static/app.js` :

```javascript
// TorrSearch front helpers, wired by event delegation from data-* attributes.
// Templates carry no inline JS: interpolated values can never run as code, and a
// strict Content-Security-Policy becomes possible later.
(function () {
  'use strict';

  // Reset one filter of the search form, then re-run the search.
  function clearFilter(name, value) {
    var form = document.getElementById('search-form');
    if (!form) return;
    if (name === 'quality' && value) {
      form.querySelectorAll('input[name="quality"]').forEach(function (cb) {
        if (cb.value === value) cb.checked = false;
      });
    } else if (name === 'min_seeders') {
      var seeders = form.querySelector('[name="min_seeders"]');
      if (seeders) seeders.value = '0';
    } else {
      var field = form.querySelector('[name="' + name + '"]');
      if (field) field.value = '';
    }
    htmx.trigger(form, 'submit');
  }

  document.addEventListener('click', function (event) {
    var copy = event.target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard.writeText(copy.dataset.copy);
      return;
    }
    var chip = event.target.closest('[data-filter]');
    if (chip) clearFilter(chip.dataset.filter, chip.dataset.value || '');
  });

  // Broken poster -> drop the <img> so the placeholder icon shows. Error events don't
  // bubble, hence the capture phase.
  document.addEventListener('error', function (event) {
    var el = event.target;
    if (el instanceof HTMLImageElement && el.hasAttribute('data-poster')) el.remove();
  }, true);
})();
```

- [ ] **Step 4 : Servir `/static`**

Dans `torsearch/web/templating.py`, ajouter sous `TEMPLATES_DIR = ...` :

```python
STATIC_DIR = Path(__file__).parent / "static"
```

Dans `torsearch/web/routes.py` :
- ajouter `from fastapi.staticfiles import StaticFiles` (après `from fastapi.responses import HTMLResponse`) ;
- remplacer `from torsearch.web.templating import templates` par `from torsearch.web.templating import STATIC_DIR, templates` ;
- dans `create_app`, juste avant `return app`, ajouter :

```python
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

Dans `torsearch/web/auth.py`, remplacer la ligne `_PUBLIC_PATHS = {"/login", "/logout"}` par :

```python
_PUBLIC_PATHS = {"/login", "/logout"}
_PUBLIC_PREFIXES = ("/static/",)


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)
```

et, dans `AuthMiddleware.dispatch`, remplacer
`if not self.settings.enabled or request.url.path in _PUBLIC_PATHS:`
par `if not self.settings.enabled or _is_public(request.url.path):`.

- [ ] **Step 5 : Mettre à jour les templates**

`torsearch/web/templates/base.html` : juste après la ligne
`<script src="https://unpkg.com/htmx.org@1.9.12"></script>`, ajouter :

```html
  <script src="/static/app.js" defer></script>
```

`torsearch/web/templates/index.html` : supprimer tout le bloc `<script> … </script>` qui définit `clearFilter` (de `<script>` jusqu'à `</script>`, juste avant `{% endblock %}`).

`torsearch/web/templates/partials/results.html` :
- remplacer la ligne
  `hx-vals='{"sort": "{{ sort }}", "dir": "{{ 'asc' if dir == 'desc' else 'desc' }}"}'`
  par
  ```html
            hx-vals='{{ {"sort": sort, "dir": ("asc" if dir == "desc" else "desc")} | tojson }}'
  ```
- remplacer les deux lignes
  ```html
  <button type="button" data-filter="{{ f.name }}"
          onclick="clearFilter('{{ f.name }}'{% if f.value is defined and f.value %}, '{{ f.value }}'{% endif %})"
  ```
  par
  ```html
  <button type="button" data-filter="{{ f.name }}"{% if f.value is defined and f.value %} data-value="{{ f.value }}"{% endif %}
  ```
- remplacer les deux lignes du bouton copier
  ```html
    <button class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-400 hover:text-emerald-400"
            aria-label="Copier le lien" onclick="navigator.clipboard.writeText('{{ r.download_url }}')"><i class="ti ti-copy"></i></button>
  ```
  par
  ```html
    <button type="button" class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-400 hover:text-emerald-400"
            aria-label="Copier le lien" data-copy="{{ r.download_url }}"><i class="ti ti-copy"></i></button>
  ```

`partials/media_results.html`, `partials/library_list.html`, `partials/series_list.html` : dans la balise `<img …>` de l'affiche, remplacer ` onerror="this.remove()"` par ` data-poster`. Commande équivalente :

```bash
sed -i '' 's/ onerror="this.remove()"/ data-poster/' torsearch/web/templates/partials/media_results.html torsearch/web/templates/partials/library_list.html torsearch/web/templates/partials/series_list.html
```

- [ ] **Step 6 : Vérifier**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests`
Expected: tout passe ; `All checks passed!`

- [ ] **Step 7 : Contrôle navigateur (serveur de dev déjà lancé)**

Ouvrir `http://localhost:8000/` : dans les requêtes réseau, `/static/app.js` répond 200 ; la console ne montre aucune erreur. Ouvrir `http://localhost:8000/library` : une affiche introuvable laisse l'icône de remplacement.

- [ ] **Step 8 : Commit**

```bash
git add torsearch/web/static/app.js torsearch/web/templating.py torsearch/web/routes.py torsearch/web/auth.py torsearch/web/templates tests/test_no_inline_js.py tests/test_web.py tests/test_discover_web.py
git commit -m "fix(web): supprimer le JS inline (XSS) au profit de static/app.js (D2)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 6 : Templates et `static/` dans le paquet (D9)

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1 : Constater le manque**

Run:
```bash
WHEEL_DIR=$(mktemp -d) && uv build --wheel -q -o "$WHEEL_DIR" && unzip -l "$WHEEL_DIR"/torsearch-*.whl | grep -cE "torsearch/web/(templates|static)/"
```
Expected: `0` (aucun template ni fichier statique dans la wheel). `uv build` construit dans un environnement isolé (le venv du worktree n'a pas pip) ; nécessite l'accès réseau pour télécharger setuptools.

- [ ] **Step 2 : Déclarer les données du paquet**

Dans `pyproject.toml`, juste après le bloc

```toml
[tool.setuptools.packages.find]
include = ["torsearch*"]
```

ajouter :

```toml
[tool.setuptools.package-data]
torsearch = ["web/templates/**/*.html", "web/static/**/*"]
```

- [ ] **Step 3 : Vérifier**

Run: la même commande qu'au Step 1.
Expected: `24` (23 templates + `app.js`).

- [ ] **Step 4 : Commit**

```bash
git add pyproject.toml
git commit -m "build: embarquer templates et static dans le paquet (D9)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 7 : Transmission asynchrone (D3)

**Files:**
- Modify: `torsearch/transmission/client.py` (réécriture)
- Modify: `torsearch/web/routes.py` (`/download`), `torsearch/web/downloads_routes.py` (réécriture), `torsearch/monitor/runner.py` (4 appels)
- Test: `tests/test_transmission.py` (réécriture) ; faux clients async dans `tests/test_monitor_runner.py`, `tests/test_web.py`, `tests/test_downloads_web.py`, `tests/test_authz.py`

- [ ] **Step 1 : Réécrire les tests du client**

Remplacer tout le contenu de `tests/test_transmission.py` par :

```python
import asyncio
import time
from types import SimpleNamespace

from torsearch.config import TransmissionConfig
from torsearch.transmission.client import TorrentInfo, TransmissionClient


class FakeRpc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.added = []

    def add_torrent(self, url, download_dir=None):
        self.added.append(url)
        self.last_download_dir = download_dir
        return SimpleNamespace(id=42)


async def test_add_returns_torrent_id_and_passes_url():
    created = {}

    def factory(**kwargs):
        client = FakeRpc(**kwargs)
        created["client"] = client
        return client

    cfg = TransmissionConfig(host="tr.local", port=9092, username="u", password="p")
    tc = TransmissionClient(cfg, client_factory=factory)
    torrent_id = await tc.add("magnet:?xt=urn:btih:XYZ")

    assert torrent_id == 42
    assert created["client"].added == ["magnet:?xt=urn:btih:XYZ"]
    assert created["client"].kwargs["host"] == "tr.local"
    assert created["client"].kwargs["port"] == 9092
    assert created["client"].kwargs["protocol"] == "http"


async def test_add_passes_download_dir():
    captured = {}

    def factory(**kwargs):
        captured["client"] = FakeRpc(**kwargs)
        return captured["client"]

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    await tc.add("magnet:?xt=urn:btih:A", download_dir="/data/films")
    assert captured["client"].last_download_dir == "/data/films"

    await tc.add("magnet:?xt=urn:btih:B")
    assert captured["client"].last_download_dir is None


async def test_https_config_uses_https_protocol():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    await TransmissionClient(TransmissionConfig(https=True), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["protocol"] == "https"


async def test_empty_credentials_become_none():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return FakeRpc(**kwargs)

    await TransmissionClient(TransmissionConfig(), client_factory=factory).add("magnet:?xt=urn:btih:A")
    assert captured["username"] is None
    assert captured["password"] is None


async def test_client_created_once_with_short_timeout():
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return FakeRpc(**kwargs)

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    await tc.add("magnet:?xt=urn:btih:A")
    await tc.add("magnet:?xt=urn:btih:B")
    assert len(created) == 1
    assert created[0]["timeout"] == 10.0


def _fake_torrent(**o):
    base = dict(id=1, name="ubuntu.iso", progress=42.5, status="downloading",
                rate_download=1000, rate_upload=50, total_size=2000)
    base.update(o)
    return SimpleNamespace(**base)


class FakeRpcFull:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.torrents = [
            _fake_torrent(id=1, name="A"),
            _fake_torrent(id=2, name="B", progress=100.0, status="seeding"),
        ]
        self.calls = []

    def get_torrents(self):
        return self.torrents

    def stop_torrent(self, tid):
        self.calls.append(("stop", tid))

    def start_torrent(self, tid):
        self.calls.append(("start", tid))

    def remove_torrent(self, tid, delete_data=False):
        self.calls.append(("remove", tid, delete_data))


def _client_with(rpc):
    return TransmissionClient(TransmissionConfig(), client_factory=lambda **k: rpc)


async def test_list_torrents_maps_fields():
    infos = await _client_with(FakeRpcFull()).list_torrents()
    assert [i.name for i in infos] == ["A", "B"]
    a = infos[0]
    assert isinstance(a, TorrentInfo)
    assert a.id == 1 and a.percent == 42.5 and a.status == "downloading"
    assert a.down_rate == 1000 and a.up_rate == 50 and a.size == 2000


async def test_pause_calls_stop_torrent():
    rpc = FakeRpcFull()
    await _client_with(rpc).pause(7)
    assert ("stop", 7) in rpc.calls


async def test_resume_calls_start_torrent():
    rpc = FakeRpcFull()
    await _client_with(rpc).resume(7)
    assert ("start", 7) in rpc.calls


async def test_remove_calls_remove_torrent_without_data():
    rpc = FakeRpcFull()
    await _client_with(rpc).remove(7)
    assert ("remove", 7, False) in rpc.calls


async def test_rpc_does_not_block_the_event_loop():
    class SlowRpc(FakeRpcFull):
        def get_torrents(self):
            time.sleep(0.3)  # blocking I/O, like the real transmission-rpc client
            return self.torrents

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    infos = await _client_with(SlowRpc()).list_torrents()
    task.cancel()
    assert [i.name for i in infos] == ["A", "B"]
    assert ticks >= 10  # the loop kept running while the RPC was in flight
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_transmission.py -q`
Expected: FAIL — `TypeError: object int can't be used in 'await' expression` (et équivalents pour les listes / `None`).

- [ ] **Step 3 : Réécrire le client**

Remplacer tout le contenu de `torsearch/transmission/client.py` par :

```python
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from transmission_rpc import Client

from torsearch.config import TransmissionConfig

T = TypeVar("T")

DEFAULT_TIMEOUT = 10.0  # seconds (transmission-rpc defaults to 30)


class TorrentInfo(BaseModel):
    id: int
    name: str
    percent: float
    status: str
    down_rate: int
    up_rate: int
    size: int


class TransmissionClient:
    """Async facade over the blocking ``transmission_rpc`` client.

    Each RPC runs in a worker thread (``asyncio.to_thread``) so a slow or unreachable
    Transmission never blocks the event loop; every call is bounded by ``timeout``.
    """

    def __init__(self, config: TransmissionConfig, client_factory=Client, timeout: float = DEFAULT_TIMEOUT):
        self._config = config
        self._client_factory = client_factory
        self._timeout = timeout
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        # Creating the client already performs a network call: do it once, even when two
        # worker threads race for it. RPC calls themselves are not serialized.
        with self._lock:
            if self._client is None:
                self._client = self._client_factory(
                    protocol="https" if self._config.https else "http",
                    host=self._config.host,
                    port=self._config.port,
                    username=self._config.username or None,
                    password=self._config.password or None,
                    timeout=self._timeout,
                )
            return self._client

    async def _run(self, fn: Callable[[Any], T]) -> T:
        return await asyncio.to_thread(lambda: fn(self._get_client()))

    async def add(self, download_url: str, download_dir: str | None = None) -> int:
        torrent = await self._run(lambda c: c.add_torrent(download_url, download_dir=download_dir))
        return torrent.id

    async def list_torrents(self) -> list[TorrentInfo]:
        torrents = await self._run(lambda c: c.get_torrents())
        return [
            TorrentInfo(
                id=t.id,
                name=t.name,
                percent=float(getattr(t, "progress", 0.0)),
                status=str(t.status),
                down_rate=int(getattr(t, "rate_download", 0)),
                up_rate=int(getattr(t, "rate_upload", 0)),
                size=int(getattr(t, "total_size", 0)),
            )
            for t in torrents
        ]

    async def pause(self, torrent_id: int) -> None:
        await self._run(lambda c: c.stop_torrent(torrent_id))

    async def resume(self, torrent_id: int) -> None:
        await self._run(lambda c: c.start_torrent(torrent_id))

    async def remove(self, torrent_id: int) -> None:
        await self._run(lambda c: c.remove_torrent(torrent_id, delete_data=False))
```

- [ ] **Step 4 : Vérifier les tests du client**

Run: `.venv/bin/pytest tests/test_transmission.py -q`
Expected: `10 passed`

- [ ] **Step 5 : Passer les appelants en `await`**

`torsearch/web/routes.py`, dans `download` : remplacer
`torrent_id = ctx.transmission.add(download_url, ctx.config.paths.for_category(cat))`
par
`torrent_id = await ctx.transmission.add(download_url, ctx.config.paths.for_category(cat))`.

`torsearch/monitor/runner.py` :
- dans `run_jellyfin_refresh` : `torrents = transmission.list_torrents()` → `torrents = await transmission.list_torrents()` ;
- dans `run_cycle` : `transmission.add(pick.download_url)` → `await transmission.add(pick.download_url)` ;
- dans `_grab_movie` : `transmission.add(pick.download_url, download_dir=config.paths.for_category(Category.MOVIES))` → même ligne précédée de `await ` ;
- dans `run_series_cycle` : `transmission.add(r.download_url, download_dir=config.paths.for_category(Category.TV))` → même ligne précédée de `await `.

Remplacer tout le contenu de `torsearch/web/downloads_routes.py` par :

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.web.templating import templates

downloads_router = APIRouter()


async def _render_list(request: Request, error: str | None = None):
    ctx: AppContext = request.app.state.ctx
    torrents = []
    if error is None:
        try:
            torrents = await ctx.transmission.list_torrents()
        except Exception as exc:
            error = f"Transmission injoignable : {exc}"
    return templates.TemplateResponse(
        request, "partials/downloads_list.html", {"torrents": torrents, "error": error}
    )


@downloads_router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request):
    return templates.TemplateResponse(request, "downloads.html", {})


@downloads_router.get("/downloads/list", response_class=HTMLResponse)
async def downloads_list(request: Request):
    return await _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/pause", response_class=HTMLResponse)
async def pause(request: Request, torrent_id: int):
    try:
        await request.app.state.ctx.transmission.pause(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {exc}")
    return await _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/resume", response_class=HTMLResponse)
async def resume(request: Request, torrent_id: int):
    try:
        await request.app.state.ctx.transmission.resume(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {exc}")
    return await _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/delete", response_class=HTMLResponse)
async def delete(request: Request, torrent_id: int):
    try:
        await request.app.state.ctx.transmission.remove(torrent_id)
    except Exception as exc:
        return await _render_list(request, error=f"Action impossible : {exc}")
    return await _render_list(request)
```

- [ ] **Step 6 : Passer les faux clients des tests en `async`**

- `tests/test_monitor_runner.py` : dans `class FakeTransmission`, `def add(self, url, download_dir=None):` → `async def add(self, url, download_dir=None):` ; dans `class FakeTransmissionList`, `def list_torrents(self):` → `async def list_torrents(self):`.
- `tests/test_web.py` : dans `class FakeTransmission`, `def add(self, download_url, download_dir=None):` → `async def add(self, download_url, download_dir=None):`.
- `tests/test_downloads_web.py` : dans `class FakeTransmission`, préfixer `async ` devant `def list_torrents`, `def pause`, `def resume` et `def remove`.
- `tests/test_authz.py` : dans `class FakeTransmission`, `def add(self, url, download_dir=None):` → `async def add(self, url, download_dir=None):`.

- [ ] **Step 7 : Suite complète + lint + typage**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests && .venv/bin/mypy`
Expected: tout passe ; `All checks passed!` ; `Success: no issues found`.

- [ ] **Step 8 : Contrôle navigateur**

Ouvrir `http://localhost:8000/downloads` avec Transmission arrêté : le bandeau « Transmission injoignable » s'affiche, et les autres pages (ex. `/library` dans un autre onglet) restent réactives pendant ce temps.

- [ ] **Step 9 : Commit**

```bash
git add torsearch/transmission/client.py torsearch/web/routes.py torsearch/web/downloads_routes.py torsearch/monitor/runner.py tests/test_transmission.py tests/test_monitor_runner.py tests/test_web.py tests/test_downloads_web.py tests/test_authz.py
git commit -m "fix(transmission): appels RPC hors de la boucle async, délai 10 s (D3)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 8 : Secrets masqués dans Réglages (D4)

**Files:**
- Modify: `torsearch/web/settings_routes.py` (`update_general`, `update_jellyfin`, `update_indexer_route`, `test_indexer_route`)
- Modify: `torsearch/web/templates/settings.html`, `torsearch/web/templates/partials/indexer_row.html`
- Test: `tests/test_settings_web.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter à la fin de `tests/test_settings_web.py` :

```python
from torsearch.config import JellyfinConfig, TransmissionConfig


def _secret_config():
    return Config(
        transmission=TransmissionConfig(password="tr-secret-pw"),
        indexers=[IndexerConfig(name="t", url="https://t/api", api_key="passkey-secret")],
        jellyfin=JellyfinConfig(url="http://jelly:8096", api_key="jf-secret-key"),
    )


def test_settings_page_never_renders_secrets(tmp_path):
    client, _, _ = _client(tmp_path, _secret_config())
    html = client.get("/settings").text
    for secret in ("tr-secret-pw", "passkey-secret", "jf-secret-key"):
        assert secret not in html
    assert "inchange si vide" in html
    assert 'autocomplete="new-password"' in html


def test_blank_secret_fields_keep_stored_values(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/general", data={"host": "h", "port": "9091", "username": "u",
                                           "password": "", "timeout_seconds": "10"})
    client.post("/settings/indexers/t", data={"name": "t", "url": "https://t2/api",
                                              "api_key": "", "auth": "query"})
    client.post("/settings/jellyfin", data={"url": "http://jelly:8096", "api_key": ""})
    assert ctx.config.transmission.password == "tr-secret-pw"
    assert ctx.config.indexers[0].api_key == "passkey-secret"
    assert ctx.config.indexers[0].url == "https://t2/api"
    assert ctx.config.jellyfin.api_key == "jf-secret-key"


def test_new_secret_value_replaces_stored_one(tmp_path):
    client, ctx, _ = _client(tmp_path, _secret_config())
    client.post("/settings/general", data={"host": "h", "port": "9091", "password": "new-pw",
                                           "timeout_seconds": "10"})
    assert ctx.config.transmission.password == "new-pw"


def test_test_indexer_uses_stored_passkey_when_blank(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://tracker1.example/api", api_key="stored-key")])
    client, _, _ = _client(tmp_path, cfg)
    with respx.mock:
        route = respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=b'<?xml version="1.0"?><caps/>')
        )
        resp = client.post("/settings/indexers/test", data={
            "name": "t", "original_name": "t", "url": "https://tracker1.example/api",
            "api_key": "", "auth": "query",
        })
    assert "OK" in resp.text
    assert route.calls.last.request.url.params["apikey"] == "stored-key"
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_settings_web.py -q`
Expected: FAIL — les secrets apparaissent dans le HTML ; les valeurs vides écrasent les secrets (`assert '' == 'tr-secret-pw'`) ; le test Tester envoie `apikey=` vide.

- [ ] **Step 3 : Conserver les secrets côté routes**

Dans `torsearch/web/settings_routes.py` :

`update_general` — remplacer la construction de `transmission` par :

```python
        transmission = TransmissionConfig(
            host=host, port=port, username=username,
            password=password or ctx.config.transmission.password,  # blank = keep (never rendered)
            https=https is not None,
        )
```

`update_jellyfin` — remplacer le corps du `try` par :

```python
    try:
        api_key = api_key or ctx.config.jellyfin.api_key  # blank = keep (never rendered)
        ctx.update_settings(set_jellyfin(ctx.config, JellyfinConfig(url=url, api_key=api_key)))
        return _toast(request, True, "Jellyfin enregistre.")
```

`update_indexer_route` — juste après la ligne `enabled = current.enabled if current else True`, ajouter :

```python
    if not api_key and current is not None:
        api_key = current.api_key  # blank = keep (never rendered)
```

`test_indexer_route` — remplacer la fonction par :

```python
@settings_router.post("/settings/indexers/test", response_class=HTMLResponse)
async def test_indexer_route(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
    original_name: str = Form(""),
):
    if not api_key and original_name:
        # The passkey is never sent to the browser: test with the stored one.
        ctx: AppContext = request.app.state.ctx
        stored = next((ix for ix in ctx.config.indexers if ix.name == original_name), None)
        if stored is not None:
            api_key = stored.api_key
    try:
        indexer = TorznabIndexer(IndexerConfig(name=name, url=url, api_key=api_key, auth=auth))
    except ValidationError as exc:
        return _toast(request, False, f"Erreur : {exc}")
    ok, message = await indexer.test()
    return _toast(request, ok, f"{name} : {message}")
```

- [ ] **Step 4 : Ne plus rendre les secrets**

`torsearch/web/templates/settings.html` — remplacer le champ mot de passe Transmission :

```html
    <label class="text-xs text-slate-400">Mot de passe<br>
      <input name="password" type="password" value="{{ config.transmission.password }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
```

par

```html
    <label class="text-xs text-slate-400">Mot de passe<br>
      <input name="password" type="password" value="" autocomplete="new-password"
             placeholder="{{ '•••••• (inchange si vide)' if config.transmission.password else '' }}"
             class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
```

et le champ clé API Jellyfin :

```html
    <label class="text-xs text-slate-400">Cle API<br>
      <input name="api_key" value="{{ config.jellyfin.api_key }}" class="mt-1 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
```

par

```html
    <label class="text-xs text-slate-400">Cle API<br>
      <input name="api_key" type="password" value="" autocomplete="new-password"
             placeholder="{{ '•••••• (inchange si vide)' if config.jellyfin.api_key else '' }}"
             class="mt-1 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
```

`torsearch/web/templates/partials/indexer_row.html` — remplacer :

```html
  <label class="text-xs text-slate-400">Passkey<br>
    <input name="api_key" value="{{ ix.api_key }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
```

par

```html
  <label class="text-xs text-slate-400">Passkey<br>
    <input name="api_key" type="password" value="" autocomplete="new-password"
           placeholder="{{ '•••••• (inchange si vide)' if ix.api_key else '' }}"
           class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
  <input type="hidden" name="original_name" value="{{ ix.name }}">
```

- [ ] **Step 5 : Vérifier**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests`
Expected: tout passe.

- [ ] **Step 6 : Contrôle navigateur**

Ouvrir `http://localhost:8000/settings` : les champs secrets sont vides avec « •••••• (inchange si vide) » quand une valeur existe ; « Afficher le code source » ne contient aucune passkey.

- [ ] **Step 7 : Commit**

```bash
git add torsearch/web/settings_routes.py torsearch/web/templates/settings.html torsearch/web/templates/partials/indexer_row.html tests/test_settings_web.py
git commit -m "fix(settings): ne plus renvoyer les secrets au navigateur (D4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 9 : Clé TMDB réglable + repli `TMDB_API_KEY` (D10)

**Files:**
- Modify: `torsearch/settings/mutations.py` (`set_metadata`)
- Modify: `torsearch/web/settings_routes.py` (route `/settings/metadata`, contexte de la page)
- Modify: `torsearch/context.py` (repli sur l'environnement)
- Modify: `torsearch/web/templates/settings.html` (section TMDB), `torsearch/web/templates/discover.html` (avertissement)
- Test: `tests/test_settings_web.py`, `tests/test_context.py`, `tests/test_discover_web.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter à la fin de `tests/test_settings_web.py` :

```python
def test_settings_page_has_tmdb_field_without_leaking_key(tmp_path):
    from torsearch.config import MetadataConfig

    client, _, _ = _client(tmp_path, Config(metadata=MetadataConfig(tmdb_api_key="tmdb-secret")))
    html = client.get("/settings").text
    assert 'name="tmdb_api_key"' in html
    assert "tmdb-secret" not in html


def test_update_metadata_sets_and_keeps_tmdb_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/settings/metadata", data={"tmdb_api_key": "k1"})
    assert resp.status_code == 200
    assert ctx.config.metadata.tmdb_api_key == "k1"
    assert ctx.tmdb.enabled is True
    client.post("/settings/metadata", data={"tmdb_api_key": ""})
    assert ctx.config.metadata.tmdb_api_key == "k1"  # blank keeps the stored key
```

Dans `tests/test_context.py`, remplacer `test_context_exposes_tmdb_disabled_by_default` par :

```python
def test_context_exposes_tmdb_disabled_by_default(tmp_path, monkeypatch):
    from torsearch.context import AppContext
    from torsearch.metadata.tmdb import TmdbClient
    from torsearch.settings.store import SettingsStore

    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    assert isinstance(ctx.tmdb, TmdbClient)
    assert ctx.tmdb.enabled is False
```

et ajouter à la fin du fichier :

```python
def test_tmdb_falls_back_to_env_when_no_stored_key(tmp_path, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "from-env")
    ctx = AppContext(SettingsStore(tmp_path / "s.json"))
    assert ctx.tmdb.enabled is True
    assert ctx.config.metadata.tmdb_api_key == ""  # the env value is never persisted


def test_stored_tmdb_key_wins_over_env(tmp_path, monkeypatch):
    from torsearch.config import MetadataConfig

    monkeypatch.setenv("TMDB_API_KEY", "from-env")
    store = SettingsStore(tmp_path / "s.json")
    store.save(Config(metadata=MetadataConfig(tmdb_api_key="stored")))
    ctx = AppContext(store)
    assert ctx.tmdb._api_key == "stored"
```

Ajouter à la fin de `tests/test_discover_web.py` :

```python
def test_discover_onboarding_points_admin_to_settings():
    resp = _client(FakeTmdb(enabled=False)).get("/discover")
    assert "Renseigne-la dans" in resp.text
    assert "TMDB_API_KEY" in resp.text
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `.venv/bin/pytest tests/test_settings_web.py tests/test_context.py tests/test_discover_web.py -q`
Expected: FAIL — pas de champ `tmdb_api_key` ; `POST /settings/metadata` → 404/405 ; repli sur l'environnement absent (`assert False is True`) ; texte « Renseigne-la dans » absent.

- [ ] **Step 3 : Mutation**

Dans `torsearch/settings/mutations.py`, ajouter `MetadataConfig` à l'import depuis `torsearch.config` (ordre alphabétique : après `LibraryConfig`), puis, après `set_jellyfin` :

```python
def set_metadata(config: Config, metadata: MetadataConfig) -> Config:
    return config.model_copy(update={"metadata": metadata})
```

- [ ] **Step 4 : Route et contexte de la page**

Dans `torsearch/web/settings_routes.py` :
- ajouter `import os` en tête (avant `from fastapi import APIRouter, Form, Request`, séparé par une ligne vide comme l'exige isort) ;
- ajouter `MetadataConfig` à l'import depuis `torsearch.config` (après `LibraryConfig`) et `set_metadata` à l'import depuis `torsearch.settings.mutations` (après `set_library`) ;
- dans `settings_page`, ajouter l'entrée `"tmdb_from_env": bool(os.environ.get("TMDB_API_KEY")),` au dictionnaire de contexte ;
- ajouter, après `update_jellyfin` :

```python
@settings_router.post("/settings/metadata", response_class=HTMLResponse)
async def update_metadata(request: Request, tmdb_api_key: str = Form("")):
    ctx: AppContext = request.app.state.ctx
    try:
        key = tmdb_api_key.strip() or ctx.config.metadata.tmdb_api_key  # blank = keep
        ctx.update_settings(set_metadata(ctx.config, MetadataConfig(tmdb_api_key=key)))
        return _toast(request, True, "Cle TMDB enregistree.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
```

- [ ] **Step 5 : Repli sur l'environnement**

Dans `torsearch/context.py` :
- ajouter `import os` en tête (avant les imports `torsearch`, séparé par une ligne vide) ;
- remplacer `from torsearch.config import Config` par `from torsearch.config import Config, MetadataConfig` ;
- dans `_rebuild`, remplacer `self._tmdb = TmdbClient(self._config.metadata)` par `self._tmdb = TmdbClient(self._effective_metadata())` ;
- ajouter la méthode :

```python
    def _effective_metadata(self) -> MetadataConfig:
        """Stored TMDB key first; else fall back to TMDB_API_KEY (never persisted)."""
        if self._config.metadata.tmdb_api_key:
            return self._config.metadata
        return MetadataConfig(tmdb_api_key=os.environ.get("TMDB_API_KEY", ""))
```

- [ ] **Step 6 : Templates**

`torsearch/web/templates/settings.html` — insérer cette section juste avant la section « Jellyfin (lecture) » (le `<section>` qui contient `ti-device-tv`) :

```html
<section class="rounded-xl border border-slate-700 bg-slate-800/40 p-5">
  <div class="mb-4 flex items-center gap-2 border-b border-slate-700/70 pb-3">
    <i class="ti ti-compass text-slate-500"></i>
    <h2 class="text-sm font-semibold text-white">Decouverte (TMDB)</h2>
  </div>
  <form hx-post="/settings/metadata" hx-target="#toast" class="flex flex-wrap items-end gap-3">
    <label class="text-xs text-slate-400">Cle API TMDB<br>
      <input name="tmdb_api_key" type="password" value="" autocomplete="new-password"
             placeholder="{% if config.metadata.tmdb_api_key %}•••••• (inchange si vide){% elif tmdb_from_env %}definie par TMDB_API_KEY{% endif %}"
             class="mt-1 w-72 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
  </form>
  <p class="mt-2 text-xs text-slate-500">Cle gratuite sur themoviedb.org (Parametres &gt; API).</p>
</section>
```

`torsearch/web/templates/discover.html` — remplacer la ligne :

```html
  <i class="ti ti-alert-triangle text-amber-400"></i> Cle TMDB absente. Renseigne <code class="rounded bg-slate-800 px-1">TMDB_API_KEY</code> pour activer la decouverte par titre.
```

par :

```html
  <i class="ti ti-alert-triangle text-amber-400"></i> Cle TMDB absente.{% if is_admin %} Renseigne-la dans <a href="/settings" class="underline text-amber-300 hover:text-amber-200">Reglages</a> (ou via la variable <code class="rounded bg-slate-800 px-1">TMDB_API_KEY</code>) pour activer la decouverte par titre.{% else %} Demande a l'administrateur de la configurer.{% endif %}
```

- [ ] **Step 7 : Vérifier**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests && .venv/bin/mypy`
Expected: tout passe.

- [ ] **Step 8 : Contrôle navigateur**

Ouvrir `http://localhost:8000/settings` : la section « Decouverte (TMDB) » est présente ; enregistrer une clé → toast « Cle TMDB enregistree. » ; `http://localhost:8000/discover` affiche alors la recherche (plus d'avertissement) et charge les tendances si la clé est valide.

- [ ] **Step 9 : Commit**

```bash
git add torsearch/settings/mutations.py torsearch/web/settings_routes.py torsearch/context.py torsearch/web/templates/settings.html torsearch/web/templates/discover.html tests/test_settings_web.py tests/test_context.py tests/test_discover_web.py
git commit -m "feat(settings): clé TMDB réglable dans Réglages + repli TMDB_API_KEY (D10)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 10 : Documentation reverse proxy (D5)

**Files:**
- Modify: `.env.example`, `docker-compose.yml`, `README.md`

- [ ] **Step 1 : `.env.example`**

Juste après la ligne `TORSEARCH_HTTPS=`, ajouter :

```
# Derriere un reverse proxy : IP (ou plage) du proxy autorise a transmettre l'IP reelle
# des clients (X-Forwarded-For). Sans ca, l'anti-brute-force voit l'IP du proxy pour tout
# le monde. Mettre * seulement si le port de TorrSearch n'est joignable que par le proxy.
# FORWARDED_ALLOW_IPS=172.18.0.0/16
```

- [ ] **Step 2 : `docker-compose.yml`**

Dans `services.torsearch.environment`, juste après la ligne `- TORSEARCH_CONFIG=/bootstrap/bootstrap.yaml`, ajouter :

```yaml
      # Derriere un reverse proxy : IP/plage du proxy (cf. .env.example).
      # - FORWARDED_ALLOW_IPS=172.18.0.0/16
```

- [ ] **Step 3 : `README.md`**

Dans la section « Sécurité & exposition », après la première puce (celle qui se termine par « pour que le cookie de session soit `Secure`. »), ajouter :

```markdown
- Derrière un reverse proxy, renseigne aussi `FORWARDED_ALLOW_IPS` (IP ou plage du
  proxy) : sinon tous les clients partagent l'IP du proxy et quelques échecs de connexion
  bloquent tout le monde.
```

- [ ] **Step 4 : Vérifier**

Run: `grep -n "FORWARDED_ALLOW_IPS" .env.example docker-compose.yml README.md`
Expected: une occurrence dans chacun des trois fichiers.

- [ ] **Step 5 : Commit**

```bash
git add .env.example docker-compose.yml README.md
git commit -m "docs: documenter FORWARDED_ALLOW_IPS derrière un reverse proxy (D5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 11 : Vérification finale et PR

- [ ] **Step 1 : Filet complet**

Run: `.venv/bin/ruff check torsearch tests && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: `All checks passed!` ; `Success: no issues found` ; tous les tests passent (environ 380).

- [ ] **Step 2 : Parcours dans le navigateur**

Sur le serveur de dev (`http://localhost:8000`) : Recherche, Découvrir, Bibliothèque, Réglages, Téléchargements, Surveillance, Demandes répondent sans erreur ; la console ne montre aucune erreur JS ; `/static/app.js` est servi.

- [ ] **Step 3 : Pousser la branche**

```bash
git push -u origin claude/project-refactor-improvements-26d124
```

- [ ] **Step 4 : Ouvrir la PR**

```bash
gh pr create --base main --title "Chantier 1 : assainissement sécurité & fiabilité" --body "$(cat <<'EOF'
Premier chantier de la refonte (1 assainissement → 2 moteur de décision → 3 suivi des téléchargements → 4 refonte UI).
Spec : docs/superpowers/specs/2026-09-24-chantier1-assainissement-design.md

## Correctifs (un commit chacun, test rouge d'abord)
- **D1** Sessions révoquées : compte supprimé → déconnecté ; rôle lu en base (rétrogradation/promotion immédiates).
- **D2** XSS : plus aucun JS inline dans les templates, comportements dans `static/app.js` (attributs `data-*`).
- **D3** Transmission ne bloque plus l'app : façade async (threads), délai 10 s.
- **D4** Réglages ne renvoie plus les secrets (champ vide = inchangé, Tester réutilise la passkey stockée).
- **D5** `FORWARDED_ALLOW_IPS` documenté (anti-brute-force derrière un reverse proxy).
- **D6** Enregistrer la surveillance ne réinitialise plus `regrab_hours`.
- **D7** Helpers de formulaire mutualisés (`web/forms.py`).
- **D8** Noms contenant `/ ? # %` refusés (ils cassaient les URLs d'édition).
- **D9** Templates et `static/` embarqués dans le paquet.
- **D10** Clé TMDB réglable dans Réglages, repli sur `TMDB_API_KEY`.

## Vérification
- ruff, mypy, pytest verts.
- Parcours manuel des pages sur le serveur local.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: l'URL de la PR s'affiche.
