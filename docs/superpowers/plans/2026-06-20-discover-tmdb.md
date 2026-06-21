# Phase A — Découverte TMDB — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une page **Découvrir** qui cherche films/séries par vrai titre via TMDB (affiche + année + résumé) et branche chaque résultat sur la recherche torrent existante.

**Architecture:** `MediaResult` (modèle) + `MetadataConfig` (clé TMDB) + `TmdbClient` (httpx async, résilient, injectable — calqué sur `TorznabIndexer`) exposé via `AppContext.tmdb` ; routes `/discover` et `/discover/search` rendant des cartes affiches, chaque carte pontant vers `/search` (réutilise `results.html`).

**Tech Stack:** FastAPI/Starlette, httpx, Jinja2/HTMX/Tailwind CDN, Tabler Icons, pytest + respx + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-20-discover-tmdb-design.md`

---

## Structure des fichiers

- **Modifier** `torsearch/models.py` — `MediaResult` (+ `poster_url`).
- **Modifier** `torsearch/config.py` — `MetadataConfig` + champ `metadata` sur `Config`.
- **Créer** `torsearch/metadata/__init__.py` (vide) et `torsearch/metadata/tmdb.py` — `parse_multi` + `TmdbClient`.
- **Modifier** `torsearch/context.py` — `AppContext.tmdb` (construit au `_rebuild`).
- **Créer** `torsearch/web/discover_routes.py` — routeur `/discover`, `/discover/search`.
- **Créer** `torsearch/web/templates/discover.html` et `templates/partials/media_results.html`.
- **Modifier** `torsearch/web/templates/base.html` — entrée nav « Decouvrir ».
- **Modifier** `torsearch/web/routes.py` — inclure `discover_router`.
- **Modifier** `.env.example`, `config.example.yaml` — documenter `TMDB_API_KEY`.
- **Tests** : `tests/test_tmdb.py`, `tests/test_discover_web.py`, ajouts à `tests/test_models.py` et `tests/test_config.py`.

---

## Task 1 : Modèle `MediaResult`

**Files:**
- Modify: `torsearch/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter à la fin de `tests/test_models.py` :

```python
from torsearch.models import MediaResult


def test_media_result_poster_url_built_from_path():
    m = MediaResult(tmdb_id=1, media_type="movie", title="Dune", poster_path="/p.jpg")
    assert m.poster_url == "https://image.tmdb.org/t/p/w342/p.jpg"


def test_media_result_poster_url_none_without_path():
    m = MediaResult(tmdb_id=2, media_type="tv", title="GoT")
    assert m.poster_url is None
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_models.py -q -k poster_url`
Expected: FAIL — `ImportError: cannot import name 'MediaResult'`

- [ ] **Step 3 : Implémenter le modèle**

Dans `torsearch/models.py`, ajouter après la classe `SearchResult` :

```python
class MediaResult(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" | "tv"
    title: str
    year: str | None = None
    overview: str = ""
    poster_path: str | None = None

    @computed_field
    @property
    def poster_url(self) -> str | None:
        if not self.poster_path:
            return None
        return f"https://image.tmdb.org/t/p/w342{self.poster_path}"
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `uv run pytest tests/test_models.py -q -k poster_url`
Expected: PASS (2 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/models.py tests/test_models.py
git commit -m "feat: add MediaResult model with poster_url"
```

---

## Task 2 : `MetadataConfig`

**Files:**
- Modify: `torsearch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1 : Écrire le test**

Ajouter à la fin de `tests/test_config.py` :

```python
def test_metadata_tmdb_key_interpolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "secret-key")
    p = tmp_path / "c.yaml"
    p.write_text("metadata:\n  tmdb_api_key: ${TMDB_API_KEY}\n")
    from torsearch.config import load_config

    cfg = load_config(p)
    assert cfg.metadata.tmdb_api_key == "secret-key"


def test_metadata_defaults_to_empty(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("{}\n")
    from torsearch.config import load_config

    assert load_config(p).metadata.tmdb_api_key == ""
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_config.py -q -k metadata`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'metadata'`

- [ ] **Step 3 : Implémenter la config**

Dans `torsearch/config.py`, ajouter la classe avant `class Config`:

```python
class MetadataConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    tmdb_api_key: str = ""
```

Puis dans `class Config`, ajouter le champ après `notifications` :

```python
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `uv run pytest tests/test_config.py -q -k metadata`
Expected: PASS (2 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add MetadataConfig with TMDB api key"
```

---

## Task 3 : `TmdbClient`

**Files:**
- Create: `torsearch/metadata/__init__.py`, `torsearch/metadata/tmdb.py`
- Test: `tests/test_tmdb.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_tmdb.py` :

```python
import httpx
import respx

from torsearch.config import MetadataConfig
from torsearch.metadata.tmdb import TmdbClient, parse_multi

SAMPLE = {
    "results": [
        {"id": 693134, "media_type": "movie", "title": "Dune : Deuxieme partie",
         "release_date": "2024-02-27", "overview": "Paul Atreides...", "poster_path": "/a.jpg"},
        {"id": 1399, "media_type": "tv", "name": "Game of Thrones",
         "first_air_date": "2011-04-17", "overview": "Neuf familles...", "poster_path": None},
        {"id": 500, "media_type": "person", "name": "Un Acteur"},
    ]
}


def test_parse_multi_maps_and_filters():
    out = parse_multi(SAMPLE)
    assert len(out) == 2
    movie = out[0]
    assert movie.media_type == "movie"
    assert movie.title == "Dune : Deuxieme partie"
    assert movie.year == "2024"
    assert movie.poster_url == "https://image.tmdb.org/t/p/w342/a.jpg"
    tv = out[1]
    assert tv.media_type == "tv"
    assert tv.title == "Game of Thrones"
    assert tv.year == "2011"
    assert tv.poster_url is None


def test_enabled_reflects_key():
    assert TmdbClient(MetadataConfig(tmdb_api_key="K")).enabled is True
    assert TmdbClient(MetadataConfig()).enabled is False


async def test_search_disabled_returns_empty_without_request():
    assert await TmdbClient(MetadataConfig()).search("dune") == []


async def test_search_success_parses_results():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(200, json=SAMPLE)
        )
        out = await client.search("dune")
    assert [m.title for m in out] == ["Dune : Deuxieme partie", "Game of Thrones"]


async def test_search_http_error_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(500)
        )
        assert await client.search("dune") == []


async def test_search_malformed_json_returns_empty():
    client = TmdbClient(MetadataConfig(tmdb_api_key="K"))
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/multi").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        assert await client.search("dune") == []
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_tmdb.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.metadata'`

- [ ] **Step 3 : Créer le package et le client**

Créer `torsearch/metadata/__init__.py` (fichier vide).

Créer `torsearch/metadata/tmdb.py` :

```python
from __future__ import annotations

import logging

import httpx

from torsearch.config import MetadataConfig
from torsearch.models import MediaResult

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"


def parse_multi(payload: dict) -> list[MediaResult]:
    out: list[MediaResult] = []
    for item in payload.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        if item.get("id") is None:
            continue
        title = item.get("title") or item.get("name") or ""
        date = item.get("release_date") or item.get("first_air_date") or ""
        out.append(
            MediaResult(
                tmdb_id=int(item["id"]),
                media_type=media_type,
                title=title,
                year=date[:4] if date else None,
                overview=item.get("overview") or "",
                poster_path=item.get("poster_path"),
            )
        )
    return out


class TmdbClient:
    def __init__(
        self,
        config: MetadataConfig,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        self._api_key = config.tmdb_api_key
        self._client = client
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[MediaResult]:
        if not self.enabled or not query.strip():
            return []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                _SEARCH_URL,
                params={
                    "api_key": self._api_key,
                    "query": query,
                    "language": "fr-FR",
                    "include_adult": "false",
                },
            )
            response.raise_for_status()
            return parse_multi(response.json())
        except Exception as exc:  # resilience: never raise to the web layer
            logger.warning("TMDB search failed: %s", exc)
            return []
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `uv run pytest tests/test_tmdb.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/metadata/__init__.py torsearch/metadata/tmdb.py tests/test_tmdb.py
git commit -m "feat: add resilient TMDB multi-search client"
```

---

## Task 4 : `AppContext.tmdb`

**Files:**
- Modify: `torsearch/context.py`
- Test: `tests/test_context.py`

- [ ] **Step 1 : Écrire le test**

Ajouter à la fin de `tests/test_context.py` :

```python
def test_context_exposes_tmdb_disabled_by_default(tmp_path):
    from torsearch.context import AppContext
    from torsearch.metadata.tmdb import TmdbClient
    from torsearch.settings.store import SettingsStore

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    assert isinstance(ctx.tmdb, TmdbClient)
    assert ctx.tmdb.enabled is False
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_context.py -q -k tmdb`
Expected: FAIL — `AttributeError: 'AppContext' object has no attribute 'tmdb'`

- [ ] **Step 3 : Câbler le contexte**

Dans `torsearch/context.py`, ajouter l'import :

```python
from torsearch.metadata.tmdb import TmdbClient
```

Ajouter la propriété après `transmission` :

```python
    @property
    def tmdb(self) -> TmdbClient:
        return self._tmdb
```

Dans `_rebuild`, ajouter à la fin :

```python
        self._tmdb = TmdbClient(self._config.metadata)
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `uv run pytest tests/test_context.py -q -k tmdb`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add torsearch/context.py tests/test_context.py
git commit -m "feat: expose TMDB client on AppContext"
```

---

## Task 5 : Pages Découvrir + nav + bridge

**Files:**
- Create: `torsearch/web/discover_routes.py`, `torsearch/web/templates/discover.html`, `torsearch/web/templates/partials/media_results.html`
- Modify: `torsearch/web/routes.py`, `torsearch/web/templates/base.html`
- Test: `tests/test_discover_web.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_discover_web.py` :

```python
import re

from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.models import MediaResult
from torsearch.web.routes import create_app


class FakeTmdb:
    def __init__(self, enabled=True, results=None):
        self.enabled = enabled
        self._results = results or []

    async def search(self, query):
        return list(self._results)


class FakeCtx:
    def __init__(self, tmdb):
        self.tmdb = tmdb
        self.config = Config()


def _client(tmdb) -> TestClient:
    return TestClient(create_app(FakeCtx(tmdb)))


def _media():
    return MediaResult(tmdb_id=693134, media_type="movie", title="Dune Deux",
                       year="2024", overview="Paul...", poster_path="/a.jpg")


def test_discover_page_shows_onboarding_without_key():
    resp = _client(FakeTmdb(enabled=False)).get("/discover")
    assert resp.status_code == 200
    assert "TMDB_API_KEY" in resp.text


def test_discover_page_shows_search_with_key():
    resp = _client(FakeTmdb(enabled=True)).get("/discover")
    assert resp.status_code == 200
    assert 'hx-get="/discover/search"' in resp.text


def test_discover_search_renders_media_cards():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert resp.status_code == 200
    assert "Dune Deux" in resp.text
    assert "2024" in resp.text


def test_discover_card_bridges_to_torrent_search():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "dune"})
    assert 'hx-get="/search"' in resp.text
    assert "Torrents" in resp.text


def test_discover_search_empty_query_shows_placeholder():
    resp = _client(FakeTmdb(results=[_media()])).get("/discover/search", params={"q": "  "})
    assert "Aucun media" in resp.text


def test_nav_marks_discover_active():
    html = _client(FakeTmdb(enabled=True)).get("/discover").text
    assert re.search(r'href="/discover"[^>]*aria-current="page"', html)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_discover_web.py -q`
Expected: FAIL — `404` / templates absents (`create_app` n'inclut pas encore `discover_router`)

- [ ] **Step 3 : Créer le routeur**

Créer `torsearch/web/discover_routes.py` :

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
        request, "partials/media_results.html", {"media": media, "query": q}
    )
```

- [ ] **Step 4 : Créer `discover.html`**

Créer `torsearch/web/templates/discover.html` :

```html
{% extends "base.html" %}
{% block content %}
{% if not has_tmdb %}
<div class="mb-5 rounded-lg border border-amber-600/40 bg-amber-600/10 px-4 py-3 text-sm">
  <i class="ti ti-alert-triangle text-amber-400"></i> Cle TMDB absente. Renseigne <code class="rounded bg-slate-800 px-1">TMDB_API_KEY</code> pour activer la decouverte par titre.
</div>
{% else %}
<form hx-get="/discover/search" hx-target="#media-results" hx-indicator="#dspin" class="mb-5">
  <div class="flex items-stretch overflow-hidden rounded-xl border border-slate-700 bg-slate-800 focus-within:border-emerald-500">
    <span class="flex items-center pl-4 text-slate-500"><i class="ti ti-movie text-lg"></i></span>
    <input type="text" name="q" placeholder="Chercher un film ou une serie par titre..." autofocus
           class="min-w-0 flex-1 bg-transparent px-3 py-3 text-slate-100 outline-none">
    <button type="submit" class="bg-emerald-500 px-5 font-semibold text-slate-900 hover:bg-emerald-400">Decouvrir</button>
    <span id="dspin" class="htmx-indicator flex items-center px-3 text-sm text-slate-400">...</span>
  </div>
</form>
{% endif %}
<div id="media-results"></div>
<div id="results" class="mt-6"></div>
{% endblock %}
```

- [ ] **Step 5 : Créer `partials/media_results.html`**

Créer `torsearch/web/templates/partials/media_results.html` :

```html
{% if not media %}
  <p class="text-slate-400">Aucun media trouve{% if query %} pour "{{ query }}"{% endif %}.</p>
{% else %}
<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
  {% for m in media %}
  <div class="overflow-hidden rounded-lg border border-slate-800 bg-slate-800/40">
    <div class="aspect-[2/3] bg-slate-900">
      {% if m.poster_url %}
      <img src="{{ m.poster_url }}" alt="{{ m.title }}" class="h-full w-full object-cover" loading="lazy">
      {% else %}
      <div class="flex h-full items-center justify-center text-slate-600"><i class="ti ti-photo text-3xl"></i></div>
      {% endif %}
    </div>
    <div class="p-2.5">
      <div class="flex items-center gap-1.5">
        <span class="rounded px-1.5 py-0.5 text-[10px] {{ 'bg-sky-500/15 text-sky-300' if m.media_type == 'movie' else 'bg-violet-500/15 text-violet-300' }}">{{ 'Film' if m.media_type == 'movie' else 'Serie' }}</span>
        {% if m.year %}<span class="text-[11px] text-slate-500">{{ m.year }}</span>{% endif %}
      </div>
      <div class="mt-1 truncate text-sm text-slate-100" title="{{ m.title }}">{{ m.title }}</div>
      <button hx-get="/search" hx-target="#results"
              hx-vals="{{ {'q': (m.title ~ ' ' ~ (m.year or '')) | trim, 'cat': ('movies' if m.media_type == 'movie' else 'tv')} | tojson }}"
              class="mt-2 flex w-full items-center justify-center gap-1 rounded bg-emerald-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500">
        <i class="ti ti-download"></i> Torrents
      </button>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 6 : Inclure le routeur dans `create_app`**

Dans `torsearch/web/routes.py`, ajouter l'import après `from torsearch.web.auth_routes import auth_router` :

```python
from torsearch.web.discover_routes import discover_router
```

Dans `create_app`, après `app.include_router(auth_router)`, ajouter :

```python
    app.include_router(discover_router)
```

- [ ] **Step 7 : Ajouter l'entrée nav dans `base.html`**

Dans `torsearch/web/templates/base.html`, juste après le lien `href="/"` (Recherche), insérer :

```html
      <a href="/discover" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path.startswith('/discover') %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path.startswith('/discover') %} aria-current="page"{% endif %}><i class="ti ti-compass"></i>Decouvrir</a>
```

- [ ] **Step 8 : Lancer, vérifier le succès**

Run: `uv run pytest tests/test_discover_web.py -q`
Expected: PASS (6 tests)

- [ ] **Step 9 : Commit**

```bash
git add torsearch/web/discover_routes.py torsearch/web/templates/discover.html torsearch/web/templates/partials/media_results.html torsearch/web/routes.py torsearch/web/templates/base.html tests/test_discover_web.py
git commit -m "feat: TMDB discover page with poster cards bridging to torrent search"
```

---

## Task 6 : Documentation des variables

**Files:**
- Modify: `.env.example`, `config.example.yaml`

- [ ] **Step 1 : Documenter `.env.example`**

Ajouter à la fin de `.env.example` :

```dotenv
# Decouverte par titre (TMDB) : cle API gratuite depuis themoviedb.org (Parametres > API).
TMDB_API_KEY=
```

- [ ] **Step 2 : Documenter `config.example.yaml`**

Lire `config.example.yaml`, puis ajouter (au niveau racine, cohérent avec le style du fichier) :

```yaml
metadata:
  tmdb_api_key: ${TMDB_API_KEY}
```

- [ ] **Step 3 : Commit**

```bash
git add .env.example config.example.yaml
git commit -m "docs: document TMDB_API_KEY for discovery"
```

---

## Task 7 : Vérification finale

- [ ] **Step 1 : Toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante (167) + nouveaux tests (models, config, tmdb, context, discover_web), aucune régression.

- [ ] **Step 2 : Vérif visuelle (optionnel, manuel)**

Lancer l'app avec une vraie clé : `TMDB_API_KEY=<cle> uv run uvicorn torsearch.main:build_app --factory --port 8000`, ouvrir `/discover`, chercher « dune », vérifier les affiches puis le bouton « Torrents ».

---

## Self-review (notes)

- **Couverture spec :** `MediaResult`+`poster_url` (T1), `MetadataConfig`+`Config` (T2), `TmdbClient`/`parse_multi`/résilience/fr-FR (T3), `AppContext.tmdb`+hot-reload (T4), pages `/discover` + `/discover/search` + cartes + onboarding + bridge `/search` + nav active (T5), doc env/yaml (T6), non-régression (T7). ✔
- **Cohérence des noms :** `MediaResult(tmdb_id, media_type, title, year, overview, poster_path, poster_url)`, `MetadataConfig.tmdb_api_key`, `TmdbClient.enabled/search`, `parse_multi`, `AppContext.tmdb`, routes `/discover` `/discover/search`, cibles `#media-results`/`#results` — identiques entre tasks. ✔
- **Pas de placeholder :** chaque step contient code/markup/commande exact. ✔
- **Note échappement :** le bridge utilise `… | tojson` dans un attribut `hx-vals="…"` ; l'autoescape Jinja encode les guillemets → robuste aux titres à apostrophes/guillemets.
