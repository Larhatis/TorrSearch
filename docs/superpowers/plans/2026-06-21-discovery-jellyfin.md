# Phase D — Tendances + Jellyfin — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher des tendances TMDB au chargement de Découvrir, et marquer « Dans Jellyfin » (+ lien Lire) les médias déjà possédés via l'API Jellyfin.

**Architecture:** `TmdbClient.trending` (réutilise `parse_multi`) + `/discover/trending` auto-chargé ; `JellyfinClient.owned()` (map `"{type}:{tmdb_id}" → item_id`, résilient) exposé via `AppContext.jellyfin` ; routes Découvrir/Bibliothèque passent `owned`+`jellyfin_url` ; cartes affichent badge + lien Lire ; config Jellyfin dans Réglages.

**Tech Stack:** FastAPI, httpx, Jinja2/HTMX, pytest + respx + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-21-discovery-jellyfin-design.md`

---

## Structure des fichiers

- **Modifier** `torsearch/metadata/tmdb.py` — `trending`.
- **Modifier** `torsearch/config.py` — `JellyfinConfig` + champ `jellyfin`.
- **Créer** `torsearch/jellyfin/__init__.py` (vide), `torsearch/jellyfin/client.py` — `JellyfinClient`.
- **Modifier** `torsearch/context.py` — `AppContext.jellyfin`.
- **Modifier** `torsearch/web/discover_routes.py`, `templates/discover.html`, `templates/partials/media_results.html`.
- **Modifier** `torsearch/web/library_routes.py`, `templates/partials/library_list.html`, `templates/partials/series_list.html`.
- **Modifier** `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `templates/settings.html`.
- **Tests** : `test_tmdb.py`, `test_jellyfin.py`, `test_config.py`, `test_context.py`, `test_discover_web.py`, `test_library_web.py`, `test_series_web.py`.

---

## Task 1 : `TmdbClient.trending`

**Files:** Modify `torsearch/metadata/tmdb.py` ; Test `tests/test_tmdb.py`

- [ ] **Step 1 : Tests**

Ajouter à `tests/test_tmdb.py` :

```python
async def test_trending_returns_media():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/trending/all/week").mock(
            return_value=httpx.Response(200, json=SAMPLE)
        )
        out = await client.trending()
    assert [m.title for m in out] == ["Dune : Deuxieme partie", "Game of Thrones"]


async def test_trending_disabled_returns_empty():
    assert await TmdbClient(MetadataConfig()).trending() == []


async def test_trending_error_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/trending/all/week").mock(
            return_value=httpx.Response(500)
        )
        assert await client.trending() == []
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_tmdb.py -q -k trending`
Expected: FAIL — `AttributeError: 'TmdbClient' object has no attribute 'trending'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/metadata/tmdb.py`, ajouter la constante sous `_SEARCH_URL` :

```python
_TRENDING_URL = "https://api.themoviedb.org/3/trending/all/week"
```

Ajouter la méthode dans `TmdbClient` (après `search`) :

```python
    async def trending(self) -> list[MediaResult]:
        if not self.enabled:
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                _TRENDING_URL, params={"api_key": self._api_key, "language": "fr-FR"}
            )
            response.raise_for_status()
            return parse_multi(response.json())
        except Exception as exc:  # resilience
            logger.warning("TMDB trending failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_tmdb.py -q`
Expected: PASS (anciens + 3 trending)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/metadata/tmdb.py tests/test_tmdb.py
git commit -m "feat: add TMDB trending endpoint"
```

---

## Task 2 : `JellyfinConfig`

**Files:** Modify `torsearch/config.py` ; Test `tests/test_config.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_config.py` :

```python
def test_jellyfin_config_defaults_and_interpolation(tmp_path, monkeypatch):
    from torsearch.config import load_config

    monkeypatch.setenv("JELLYFIN_KEY", "secret")
    p = tmp_path / "c.yaml"
    p.write_text("jellyfin:\n  url: http://jelly:8096\n  api_key: ${JELLYFIN_KEY}\n")
    cfg = load_config(p)
    assert cfg.jellyfin.url == "http://jelly:8096"
    assert cfg.jellyfin.api_key == "secret"
    empty = tmp_path / "e.yaml"
    empty.write_text("{}\n")
    assert load_config(empty).jellyfin.url == ""
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_config.py -q -k jellyfin`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'jellyfin'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/config.py`, ajouter avant `class Config` :

```python
class JellyfinConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = ""
    api_key: str = ""
```

Et dans `class Config`, après `library` :

```python
    jellyfin: JellyfinConfig = Field(default_factory=JellyfinConfig)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_config.py -q -k jellyfin`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add JellyfinConfig"
```

---

## Task 3 : `JellyfinClient`

**Files:** Create `torsearch/jellyfin/__init__.py`, `torsearch/jellyfin/client.py` ; Test `tests/test_jellyfin.py`

- [ ] **Step 1 : Tests**

Créer `tests/test_jellyfin.py` :

```python
import httpx
import respx

from torsearch.config import JellyfinConfig
from torsearch.jellyfin.client import JellyfinClient

SAMPLE = {"Items": [
    {"Id": "aaa", "Type": "Movie", "Name": "Dune", "ProviderIds": {"Tmdb": "438631"}},
    {"Id": "bbb", "Type": "Series", "Name": "GoT", "ProviderIds": {"Tmdb": "1399"}},
    {"Id": "ccc", "Type": "Movie", "Name": "NoProvider", "ProviderIds": {}},
]}


def test_enabled_and_base_url():
    c = JellyfinClient(JellyfinConfig(url="http://jelly/", api_key="K"))
    assert c.enabled is True
    assert c.base_url == "http://jelly"
    assert JellyfinClient(JellyfinConfig()).enabled is False


async def test_owned_disabled_returns_empty():
    assert await JellyfinClient(JellyfinConfig()).owned() == {}


async def test_owned_parses_provider_ids():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Items").mock(return_value=httpx.Response(200, json=SAMPLE))
        owned = await c.owned()
    assert owned == {"movie:438631": "aaa", "tv:1399": "bbb"}


async def test_owned_http_error_returns_empty():
    c = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/Items").mock(return_value=httpx.Response(500))
        assert await c.owned() == {}
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_jellyfin.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.jellyfin'`

- [ ] **Step 3 : Implémenter**

Créer `torsearch/jellyfin/__init__.py` (vide).

Créer `torsearch/jellyfin/client.py` :

```python
from __future__ import annotations

import logging

import httpx

from torsearch.config import JellyfinConfig

logger = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self, config: JellyfinConfig, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self._url = config.url.rstrip("/")
        self._api_key = config.api_key
        self._client = client
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._api_key)

    @property
    def base_url(self) -> str:
        return self._url

    async def owned(self) -> dict[str, str]:
        if not self.enabled:
            return {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._url}/Items",
                params={
                    "Recursive": "true", "IncludeItemTypes": "Movie,Series",
                    "Fields": "ProviderIds", "api_key": self._api_key,
                },
            )
            response.raise_for_status()
            result: dict[str, str] = {}
            for item in response.json().get("Items", []):
                tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
                if not tmdb:
                    continue
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                result[f"{media_type}:{tmdb}"] = item.get("Id", "")
            return result
        except Exception as exc:  # resilience: never raise to the web layer
            logger.warning("Jellyfin owned() failed: %s", exc)
            return {}
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_jellyfin.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/jellyfin/__init__.py torsearch/jellyfin/client.py tests/test_jellyfin.py
git commit -m "feat: add resilient Jellyfin owned-items client"
```

---

## Task 4 : `AppContext.jellyfin`

**Files:** Modify `torsearch/context.py` ; Test `tests/test_context.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_context.py` :

```python
def test_context_exposes_jellyfin_disabled_by_default(tmp_path):
    from torsearch.context import AppContext
    from torsearch.jellyfin.client import JellyfinClient
    from torsearch.settings.store import SettingsStore

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    assert isinstance(ctx.jellyfin, JellyfinClient)
    assert ctx.jellyfin.enabled is False
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_context.py -q -k jellyfin`
Expected: FAIL — `AttributeError: 'AppContext' object has no attribute 'jellyfin'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/context.py`, ajouter l'import :

```python
from torsearch.jellyfin.client import JellyfinClient
```

Ajouter la propriété après `tmdb` :

```python
    @property
    def jellyfin(self) -> JellyfinClient:
        return self._jellyfin
```

Dans `_rebuild`, ajouter à la fin :

```python
        self._jellyfin = JellyfinClient(self._config.jellyfin)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_context.py -q -k jellyfin`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add torsearch/context.py tests/test_context.py
git commit -m "feat: expose Jellyfin client on AppContext"
```

---

## Task 5 : Découvrir — tendances + marqueurs Jellyfin

**Files:** Modify `torsearch/web/discover_routes.py`, `templates/discover.html`, `templates/partials/media_results.html` ; Test `tests/test_discover_web.py`

- [ ] **Step 1 : Mettre à jour les fixtures + tests**

Dans `tests/test_discover_web.py`, remplacer les classes `FakeTmdb` et `FakeCtx` et le helper `_client` par :

```python
class FakeTmdb:
    def __init__(self, enabled=True, results=None):
        self.enabled = enabled
        self._results = results or []

    async def search(self, query):
        return list(self._results)

    async def trending(self):
        return list(self._results)


class FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)


class FakeCtx:
    def __init__(self, tmdb, jellyfin=None):
        self.tmdb = tmdb
        self.config = Config()
        self.jellyfin = jellyfin or FakeJellyfin()


def _client(tmdb, jellyfin=None) -> TestClient:
    return TestClient(create_app(FakeCtx(tmdb, jellyfin)))
```

Ajouter ces tests à la fin de `tests/test_discover_web.py` :

```python
def test_discover_page_autoloads_trending():
    resp = _client(FakeTmdb(enabled=True)).get("/discover")
    assert 'hx-get="/discover/trending"' in resp.text


def test_discover_trending_renders_cards():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/trending")
    assert resp.status_code == 200
    assert "Dune Deux" in resp.text


def test_discover_marks_owned_in_jellyfin():
    jelly = FakeJellyfin(owned={"movie:693134": "item-xyz"})
    resp = _client(FakeTmdb(results=[_media()]), jelly).get("/discover/search", params={"q": "dune"})
    assert "Dans Jellyfin" in resp.text
    assert "item-xyz" in resp.text
```

(`_media()` existe déjà et renvoie un film `tmdb_id=693134`.)

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_discover_web.py -q -k "autoloads or trending or owned"`
Expected: FAIL — route `/discover/trending` absente / `ctx.jellyfin` non utilisé

- [ ] **Step 3 : Routes Découvrir**

Remplacer `torsearch/web/discover_routes.py` par :

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.web.templating import templates

discover_router = APIRouter()


@discover_router.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(request, "discover.html", {"has_tmdb": ctx.tmdb.enabled})


@discover_router.get("/discover/search", response_class=HTMLResponse)
async def discover_search(request: Request, q: str = ""):
    ctx = request.app.state.ctx
    media = await ctx.tmdb.search(q) if q.strip() else []
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {"media": media, "query": q, "owned": await ctx.jellyfin.owned(),
         "jellyfin_url": ctx.jellyfin.base_url},
    )


@discover_router.get("/discover/trending", response_class=HTMLResponse)
async def discover_trending(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(
        request, "partials/media_results.html",
        {"media": await ctx.tmdb.trending(), "query": "", "owned": await ctx.jellyfin.owned(),
         "jellyfin_url": ctx.jellyfin.base_url},
    )
```

- [ ] **Step 4 : Auto-chargement des tendances**

Dans `torsearch/web/templates/discover.html`, remplacer la ligne
`<div id="media-results"></div>` par :

```html
<div id="media-results"{% if has_tmdb %} hx-get="/discover/trending" hx-trigger="load"{% endif %}></div>
```

- [ ] **Step 5 : Marqueurs Jellyfin sur les cartes**

Dans `torsearch/web/templates/partials/media_results.html`, à l'intérieur de la boucle `{% for m in media %}`, juste après la ligne d'ouverture `<div class="p-2.5">`, ajouter :

```html
      {% set jf = (owned or {}).get(m.media_type ~ ':' ~ m.tmdb_id) %}
```

Dans le bloc `<div class="flex items-center gap-1.5">` (badges type/année), ajouter avant sa
fermeture `</div>` :

```html
        {% if jf %}<span class="rounded px-1.5 py-0.5 text-[10px] bg-emerald-500/15 text-emerald-300">Dans Jellyfin</span>{% endif %}
```

Et juste après la ligne du titre `<div class="mt-1 truncate text-sm text-slate-100" title="{{ m.title }}">{{ m.title }}</div>`, ajouter :

```html
      {% if jf %}
      <a href="{{ jellyfin_url }}/web/#/details?id={{ jf }}" target="_blank" rel="noopener"
         class="mt-1.5 flex w-full items-center justify-center gap-1 rounded bg-emerald-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500">
        <i class="ti ti-player-play"></i> Lire
      </a>
      {% endif %}
```

- [ ] **Step 6 : Vérifier le succès**

Run: `uv run pytest tests/test_discover_web.py -q`
Expected: PASS (anciens + 3 nouveaux)

- [ ] **Step 7 : Commit**

```bash
git add torsearch/web/discover_routes.py torsearch/web/templates/discover.html torsearch/web/templates/partials/media_results.html tests/test_discover_web.py
git commit -m "feat: trending discovery landing and Jellyfin owned markers"
```

---

## Task 6 : Marqueurs Jellyfin sur la Bibliothèque

**Files:** Modify `torsearch/web/library_routes.py`, `templates/partials/library_list.html`, `templates/partials/series_list.html` ; Test `tests/test_library_web.py`, `tests/test_series_web.py`

- [ ] **Step 1 : Mettre à jour les fixtures + test**

Dans `tests/test_library_web.py` **et** `tests/test_series_web.py`, ajouter dans chaque classe
`FakeCtx.__init__` la ligne (après `self.config = ...`) :

```python
        self.jellyfin = _FakeJellyfin()
```

et, en tête de chaque fichier (après les imports), définir :

```python
class _FakeJellyfin:
    base_url = "http://jelly"

    def __init__(self, owned=None):
        self._owned = owned or {}

    async def owned(self):
        return dict(self._owned)
```

Ajouter ce test à `tests/test_library_web.py` :

```python
def test_library_marks_owned_movie(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=693134, title="Dune", year="2024", added_at=NOW))
    client.app.state.ctx.jellyfin = _FakeJellyfin(owned={"movie:693134": "it-1"})
    html = client.get("/library").text
    assert "Dans Jellyfin" in html
    assert "it-1" in html
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_library_web.py -q -k owned_movie`
Expected: FAIL — `AttributeError: ... 'jellyfin'` puis (après fixtures) marqueur absent

- [ ] **Step 3 : `library_page` passe `owned`**

Dans `torsearch/web/library_routes.py`, remplacer le corps de `library_page` :

```python
@library_router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    ctx = request.app.state.ctx
    library = request.app.state.library
    series_library = request.app.state.series_library
    return templates.TemplateResponse(
        request, "library.html",
        {"movies": library.list(), "series": series_library.list(),
         "monitor_on": ctx.config.monitor.enabled,
         "owned": await ctx.jellyfin.owned(), "jellyfin_url": ctx.jellyfin.base_url},
    )
```

- [ ] **Step 4 : Marqueur sur les cartes film**

Dans `torsearch/web/templates/partials/library_list.html`, après `<div class="p-2.5">`, ajouter :

```html
      {% set jf = (owned or {}).get('movie:' ~ m.tmdb_id) %}
```

Dans le bloc des badges (après le `{% if m.year %}…{% endif %}`), ajouter :

```html
        {% if jf %}<span class="rounded px-1.5 py-0.5 text-[10px] bg-emerald-500/15 text-emerald-300">Dans Jellyfin</span>{% endif %}
```

Après la ligne du titre, ajouter :

```html
      {% if jf %}
      <a href="{{ jellyfin_url }}/web/#/details?id={{ jf }}" target="_blank" rel="noopener"
         class="mt-1.5 flex w-full items-center justify-center gap-1 rounded bg-emerald-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500">
        <i class="ti ti-player-play"></i> Lire
      </a>
      {% endif %}
```

- [ ] **Step 5 : Marqueur sur les cartes série**

Dans `torsearch/web/templates/partials/series_list.html`, après `<div class="p-2.5">`, ajouter :

```html
      {% set jf = (owned or {}).get('tv:' ~ s.tmdb_id) %}
```

Dans le bloc des badges (après le `{% if s.year %}…{% endif %}`), ajouter :

```html
        {% if jf %}<span class="rounded px-1.5 py-0.5 text-[10px] bg-emerald-500/15 text-emerald-300">Dans Jellyfin</span>{% endif %}
```

Après la ligne du titre, ajouter :

```html
      {% if jf %}
      <a href="{{ jellyfin_url }}/web/#/details?id={{ jf }}" target="_blank" rel="noopener"
         class="mt-1.5 flex w-full items-center justify-center gap-1 rounded bg-emerald-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500">
        <i class="ti ti-player-play"></i> Lire
      </a>
      {% endif %}
```

- [ ] **Step 6 : Vérifier le succès**

Run: `uv run pytest tests/test_library_web.py tests/test_series_web.py -q`
Expected: PASS (anciens + marqueur possédé)

- [ ] **Step 7 : Commit**

```bash
git add torsearch/web/library_routes.py torsearch/web/templates/partials/library_list.html torsearch/web/templates/partials/series_list.html tests/test_library_web.py tests/test_series_web.py
git commit -m "feat: Jellyfin owned markers on the library"
```

---

## Task 7 : Config Jellyfin dans Réglages

**Files:** Modify `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `templates/settings.html` ; Test `tests/test_settings_web.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_settings_web.py` (helper de build d'app autonome) :

```python
def test_update_jellyfin_settings(tmp_path):
    from fastapi.testclient import TestClient

    from torsearch.context import AppContext
    from torsearch.settings.store import SettingsStore
    from torsearch.web.routes import create_app

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx))
    resp = client.post("/settings/jellyfin", data={"url": "http://jelly:8096", "api_key": "K"})
    assert resp.status_code == 200
    assert ctx.config.jellyfin.url == "http://jelly:8096"
    assert ctx.config.jellyfin.api_key == "K"
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_settings_web.py -q -k jellyfin`
Expected: FAIL — `404 Not Found` pour `/settings/jellyfin`

- [ ] **Step 3 : Mutation `set_jellyfin`**

Dans `torsearch/settings/mutations.py`, ajouter `JellyfinConfig` à la ligne d'import depuis
`torsearch.config`, puis ajouter à la fin :

```python
def set_jellyfin(config: Config, jellyfin: JellyfinConfig) -> Config:
    return config.model_copy(update={"jellyfin": jellyfin})
```

- [ ] **Step 4 : Route `POST /settings/jellyfin`**

Dans `torsearch/web/settings_routes.py`, ajouter `JellyfinConfig` à l'import depuis
`torsearch.config` et `set_jellyfin` à l'import depuis `torsearch.settings.mutations`. Ajouter
à la fin :

```python
@settings_router.post("/settings/jellyfin", response_class=HTMLResponse)
async def update_jellyfin(request: Request, url: str = Form(""), api_key: str = Form("")):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(set_jellyfin(ctx.config, JellyfinConfig(url=url, api_key=api_key)))
        return _toast(request, True, "Jellyfin enregistre.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
```

- [ ] **Step 5 : Section Réglages**

Dans `torsearch/web/templates/settings.html`, avant `{% endblock %}`, ajouter :

```html
<section class="mt-10">
  <h2 class="font-semibold mb-2">Jellyfin (lecture)</h2>
  <form hx-post="/settings/jellyfin" hx-target="#toast" class="flex flex-wrap items-end gap-3">
    <label class="text-xs text-slate-400">URL<br>
      <input name="url" value="{{ config.jellyfin.url }}" placeholder="http://jellyfin:8096" class="mt-1 w-72 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400">Cle API<br>
      <input name="api_key" value="{{ config.jellyfin.api_key }}" class="mt-1 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
  </form>
</section>
```

- [ ] **Step 6 : Vérifier le succès**

Run: `uv run pytest tests/test_settings_web.py -q`
Expected: PASS

- [ ] **Step 7 : Commit**

```bash
git add torsearch/settings/mutations.py torsearch/web/settings_routes.py torsearch/web/templates/settings.html tests/test_settings_web.py
git commit -m "feat: configure Jellyfin connection in settings"
```

---

## Task 8 : Vérification finale

- [ ] **Step 1 : Toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante (226) + nouveaux (tmdb trending, jellyfin, config, context, discover, library/series markers, settings), aucune régression.

- [ ] **Step 2 : Vérif visuelle (optionnel, manuel)**

Lancer avec clé TMDB (+ Jellyfin configuré dans Réglages) : `/discover` montre les tendances ;
les médias présents dans Jellyfin portent « Dans Jellyfin » + bouton « Lire ».

---

## Self-review (notes)

- **Couverture spec :** `trending` (T1), `JellyfinConfig` (T2), `JellyfinClient.owned` (T3),
  `AppContext.jellyfin` (T4), tendances auto-chargées + marqueurs Découvrir (T5), marqueurs
  Bibliothèque films & séries (T6), config Jellyfin Réglages (T7), non-régression (T8). ✔
- **Cohérence des noms :** `TmdbClient.trending`, `JellyfinConfig(url,api_key)`,
  `JellyfinClient.enabled/base_url/owned`, clé `"{media_type}:{tmdb_id}"`, `AppContext.jellyfin`,
  `set_jellyfin`, contexte template `owned`/`jellyfin_url`, route `/discover/trending`
  `/settings/jellyfin`. ✔
- **Pas de placeholder :** code/markup/commandes exacts.
- **Note tolérance :** les templates utilisent `(owned or {}).get(...)` → pas d'erreur si un
  appelant (ex. re-render après remove) ne passe pas `owned`.
