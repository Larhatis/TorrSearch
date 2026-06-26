# Réglages via l'UI (v1.1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre d'éditer toute la configuration (trackers, Transmission, recherche) depuis une page web « Réglages », avec application immédiate (hot-reload) et un bouton « Tester » par tracker.

**Architecture:** Une source de vérité `data/settings.json` gérée par un `SettingsStore` (amorcée depuis `config.yaml` au 1er démarrage). Un conteneur `AppContext` possède la config + les services (`SearchService`, `TransmissionClient`) et les reconstruit en mémoire à chaque sauvegarde. Des routes HTMX `/settings/*` lisent/écrivent via le contexte. Les mutations de config sont des fonctions pures et testables.

**Tech Stack:** Python 3.12+ (3.14 en local) · FastAPI · Pydantic v2 · httpx + respx · defusedxml · Jinja2 + HTMX · pytest (asyncio auto).

**Base :** branche `feat/settings-ui` (par-dessus `feat/v1`). Toutes les commandes via `.venv/bin/python -m pytest ...`. Le code v1 existant est : `torsearch/config.py` (`Config`, `IndexerConfig`, `TransmissionConfig`, `SearchConfig`, `AuthMode`, `load_config`), `torsearch/indexers/registry.py` (`build_indexers`), `torsearch/search/service.py` (`SearchService` avec `.indexers`), `torsearch/transmission/client.py` (`TransmissionClient`), `torsearch/web/routes.py` (`create_app`, routes), `torsearch/main.py` (`build_app`, `get_app`).

---

## File Structure

| Fichier | Action / responsabilité |
|---|---|
| `torsearch/settings/__init__.py` | Créer (vide). |
| `torsearch/settings/store.py` | `SettingsStore` — persistance `data/settings.json` + amorçage. |
| `torsearch/settings/mutations.py` | Fonctions pures de mutation de `Config` + `SettingsError`. |
| `torsearch/context.py` | `AppContext` — possède config + services, hot-reload. |
| `torsearch/web/templating.py` | Objet `templates` partagé (évite l'import circulaire). |
| `torsearch/web/settings_routes.py` | Router HTMX `/settings/*`. |
| `torsearch/web/templates/settings.html` | Page Réglages. |
| `torsearch/web/templates/partials/indexer_list.html` | Liste des trackers (cible HTMX). |
| `torsearch/web/templates/partials/indexer_row.html` | Une ligne tracker éditable. |
| `torsearch/indexers/torznab.py` | Modifier — `+ async def test()`. |
| `torsearch/web/routes.py` | Modifier — `create_app(ctx)`, services via `ctx`, `templates` partagé. |
| `torsearch/web/templates/base.html` | Modifier — nav « Trackers » → « Réglages ». |
| `torsearch/web/templates/trackers.html` | Supprimer (Task 6). |
| `torsearch/main.py` | Modifier — `build_app` construit `SettingsStore` + `AppContext`. |
| `.gitignore` · `docker-compose.yml` · `README.md` · `config.example.yaml` | Modifier (Task 8). |
| `tests/test_settings_store.py` · `test_settings_mutations.py` · `test_context.py` · `test_torznab_test.py` · `test_settings_web.py` | Créer. |
| `tests/test_web.py` · `tests/test_main.py` | Modifier (Task 5/6). |

---

## Task 1: SettingsStore

**Files:**
- Create: `torsearch/settings/__init__.py` (empty), `torsearch/settings/store.py`
- Test: `tests/test_settings_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings_store.py`:
```python
from torsearch.config import Config, IndexerConfig
from torsearch.settings.store import SettingsStore


def test_load_returns_empty_config_when_no_files(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    cfg = store.load()
    assert isinstance(cfg, Config)
    assert cfg.indexers == []


def test_load_bootstraps_from_config_yaml_and_resolves_env(tmp_path, monkeypatch):
    monkeypatch.setenv("K", "secret")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: t\n    url: https://x/api\n    api_key: ${K}\n")
    settings_path = tmp_path / "data" / "settings.json"
    store = SettingsStore(settings_path, bootstrap_config_path=yaml_path)
    cfg = store.load()
    assert cfg.indexers[0].api_key == "secret"
    assert settings_path.exists()
    assert "secret" in settings_path.read_text()
    assert "${K}" not in settings_path.read_text()


def test_existing_settings_take_precedence_over_bootstrap(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        Config(indexers=[IndexerConfig(name="from_settings", url="https://s/api", api_key="k")]).model_dump_json()
    )
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("indexers:\n  - name: from_yaml\n    url: https://y/api\n    api_key: k\n")
    store = SettingsStore(settings_path, bootstrap_config_path=yaml_path)
    assert [ix.name for ix in store.load().indexers] == ["from_settings"]


def test_save_round_trips(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    store.save(Config(indexers=[IndexerConfig(name="a", url="https://a/api", api_key="key")]))
    loaded = store.load()
    assert loaded.indexers[0].name == "a"
    assert loaded.indexers[0].api_key == "key"


def test_save_is_atomic_no_tmp_left(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    store.save(Config())
    assert settings_path.exists()
    assert not settings_path.with_name(settings_path.name + ".tmp").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.settings'`.

- [ ] **Step 3: Write minimal implementation**

Create empty `torsearch/settings/__init__.py`.

`torsearch/settings/store.py`:
```python
from __future__ import annotations

import json
import os
from pathlib import Path

from torsearch.config import Config, load_config


class SettingsStore:
    def __init__(
        self,
        settings_path: str | Path,
        bootstrap_config_path: str | Path | None = None,
    ):
        self._settings_path = Path(settings_path)
        self._bootstrap_config_path = Path(bootstrap_config_path) if bootstrap_config_path else None

    def load(self) -> Config:
        if self._settings_path.exists():
            return Config(**json.loads(self._settings_path.read_text()))
        if self._bootstrap_config_path and self._bootstrap_config_path.exists():
            config = load_config(self._bootstrap_config_path)
            self.save(config)
            return config
        return Config()

    def save(self, config: Config) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._settings_path.with_name(self._settings_path.name + ".tmp")
        tmp.write_text(config.model_dump_json(indent=2))
        os.replace(tmp, self._settings_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/settings/__init__.py torsearch/settings/store.py tests/test_settings_store.py
git commit -m "feat: add SettingsStore with json persistence and bootstrap"
```

---

## Task 2: Mutations de config

**Files:**
- Create: `torsearch/settings/mutations.py`
- Test: `tests/test_settings_mutations.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings_mutations.py`:
```python
import pytest

from torsearch.config import Config, IndexerConfig, SearchConfig, TransmissionConfig
from torsearch.settings.mutations import (
    SettingsError,
    add_indexer,
    remove_indexer,
    set_general,
    set_indexer_enabled,
    update_indexer,
)


def _ix(name, **o):
    base = dict(name=name, url=f"https://{name}/api", api_key="k")
    base.update(o)
    return IndexerConfig(**base)


def test_add_indexer_appends_without_mutating_original():
    cfg = Config(indexers=[_ix("a")])
    new = add_indexer(cfg, _ix("b"))
    assert [i.name for i in new.indexers] == ["a", "b"]
    assert [i.name for i in cfg.indexers] == ["a"]  # original untouched


def test_add_indexer_rejects_duplicate_name():
    cfg = Config(indexers=[_ix("a")])
    with pytest.raises(SettingsError):
        add_indexer(cfg, _ix("a"))


def test_update_indexer_replaces_in_place():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    new = update_indexer(cfg, "a", _ix("a", url="https://new/api"))
    assert new.indexers[0].url == "https://new/api"
    assert [i.name for i in new.indexers] == ["a", "b"]


def test_update_indexer_missing_raises():
    with pytest.raises(SettingsError):
        update_indexer(Config(), "nope", _ix("nope"))


def test_update_indexer_rename_collision_raises():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    with pytest.raises(SettingsError):
        update_indexer(cfg, "a", _ix("b"))  # renaming a -> b collides


def test_remove_indexer():
    cfg = Config(indexers=[_ix("a"), _ix("b")])
    assert [i.name for i in remove_indexer(cfg, "a").indexers] == ["b"]


def test_remove_indexer_missing_raises():
    with pytest.raises(SettingsError):
        remove_indexer(Config(), "nope")


def test_set_indexer_enabled():
    cfg = Config(indexers=[_ix("a", enabled=True)])
    assert set_indexer_enabled(cfg, "a", False).indexers[0].enabled is False


def test_set_general_replaces_transmission_and_search():
    cfg = Config(indexers=[_ix("a")])
    new = set_general(cfg, TransmissionConfig(host="h", port=1), SearchConfig(timeout_seconds=2))
    assert new.transmission.host == "h"
    assert new.search.timeout_seconds == 2
    assert [i.name for i in new.indexers] == ["a"]  # indexers preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.settings.mutations'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/settings/mutations.py`:
```python
from __future__ import annotations

from torsearch.config import Config, IndexerConfig, SearchConfig, TransmissionConfig


class SettingsError(Exception):
    """Raised when a settings mutation is invalid (e.g. duplicate tracker name)."""


def _index_of(config: Config, name: str) -> int:
    for i, ix in enumerate(config.indexers):
        if ix.name == name:
            return i
    return -1


def add_indexer(config: Config, indexer: IndexerConfig) -> Config:
    if _index_of(config, indexer.name) != -1:
        raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
    return config.model_copy(update={"indexers": [*config.indexers, indexer]})


def update_indexer(config: Config, name: str, indexer: IndexerConfig) -> Config:
    idx = _index_of(config, name)
    if idx == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    if indexer.name != name and _index_of(config, indexer.name) != -1:
        raise SettingsError(f"Un tracker nommé « {indexer.name} » existe déjà.")
    new_indexers = list(config.indexers)
    new_indexers[idx] = indexer
    return config.model_copy(update={"indexers": new_indexers})


def remove_indexer(config: Config, name: str) -> Config:
    if _index_of(config, name) == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    new_indexers = [ix for ix in config.indexers if ix.name != name]
    return config.model_copy(update={"indexers": new_indexers})


def set_indexer_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _index_of(config, name)
    if idx == -1:
        raise SettingsError(f"Tracker introuvable : « {name} ».")
    new_indexers = list(config.indexers)
    new_indexers[idx] = new_indexers[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"indexers": new_indexers})


def set_general(config: Config, transmission: TransmissionConfig, search: SearchConfig) -> Config:
    return config.model_copy(update={"transmission": transmission, "search": search})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/settings/mutations.py tests/test_settings_mutations.py
git commit -m "feat: add pure config mutation helpers"
```

---

## Task 3: AppContext (hot-reload)

**Files:**
- Create: `torsearch/context.py`
- Test: `tests/test_context.py`

- [ ] **Step 1: Write the failing test**

`tests/test_context.py`:
```python
from torsearch.config import Config, IndexerConfig, SearchConfig
from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore


def test_builds_services_from_loaded_config(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Config(indexers=[IndexerConfig(name="a", url="https://a/api", api_key="k")]))
    ctx = AppContext(store)
    assert [ix.name for ix in ctx.search_service.indexers] == ["a"]
    assert ctx.transmission is not None
    assert ctx.config.indexers[0].name == "a"


def test_update_settings_persists_and_rebuilds(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    assert ctx.search_service.indexers == []
    new = Config(
        search=SearchConfig(timeout_seconds=3),
        indexers=[IndexerConfig(name="b", url="https://b/api", api_key="k")],
    )
    ctx.update_settings(new)
    assert [ix.name for ix in ctx.search_service.indexers] == ["b"]
    assert [ix.name for ix in store.load().indexers] == ["b"]  # persisted


def test_disabled_indexers_excluded_from_search_but_kept_in_config(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ctx = AppContext(store)
    ctx.update_settings(Config(indexers=[
        IndexerConfig(name="on", url="https://on/api", api_key="k", enabled=True),
        IndexerConfig(name="off", url="https://off/api", api_key="k", enabled=False),
    ]))
    assert [ix.name for ix in ctx.search_service.indexers] == ["on"]
    assert [ix.name for ix in ctx.config.indexers] == ["on", "off"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.context'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/context.py`:
```python
from __future__ import annotations

from torsearch.config import Config
from torsearch.indexers.registry import build_indexers
from torsearch.search.service import SearchService
from torsearch.settings.store import SettingsStore
from torsearch.transmission.client import TransmissionClient


class AppContext:
    def __init__(self, store: SettingsStore):
        self._store = store
        self._config = store.load()
        self._rebuild()

    @property
    def config(self) -> Config:
        return self._config

    @property
    def search_service(self) -> SearchService:
        return self._search_service

    @property
    def transmission(self) -> TransmissionClient:
        return self._transmission

    def _rebuild(self) -> None:
        indexers = build_indexers(self._config)
        self._search_service = SearchService(indexers, timeout=self._config.search.timeout_seconds)
        self._transmission = TransmissionClient(self._config.transmission)

    def update_settings(self, new_config: Config) -> None:
        self._store.save(new_config)
        self._config = new_config
        self._rebuild()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_context.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/context.py tests/test_context.py
git commit -m "feat: add AppContext with settings hot-reload"
```

---

## Task 4: Test de connexion sur TorznabIndexer

**Files:**
- Modify: `torsearch/indexers/torznab.py` (append `test` method)
- Test: `tests/test_torznab_test.py`

- [ ] **Step 1: Write the failing test**

`tests/test_torznab_test.py`:
```python
import httpx
import respx

from torsearch.config import IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer

CAPS_OK = b'<?xml version="1.0"?><caps><server/></caps>'


def _cfg(**o):
    base = dict(name="t", url="https://t/api", api_key="KEY")
    base.update(o)
    return IndexerConfig(**base)


async def test_returns_ok_on_valid_caps():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(200, content=CAPS_OK))
        ok, msg = await ix.test()
    assert ok is True
    assert msg == "OK"


async def test_reports_rejected_key_on_401():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(401))
        ok, msg = await ix.test()
    assert ok is False
    assert "refus" in msg.lower()


async def test_reports_unexpected_response_on_non_caps_xml():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        respx.get("https://t/api").mock(return_value=httpx.Response(200, content=b"<html>nope</html>"))
        ok, msg = await ix.test()
    assert ok is False


async def test_sends_caps_query_with_apikey():
    ix = TorznabIndexer(_cfg())
    with respx.mock:
        route = respx.get("https://t/api").mock(return_value=httpx.Response(200, content=CAPS_OK))
        await ix.test()
    url = str(route.calls.last.request.url)
    assert "t=caps" in url
    assert "apikey=KEY" in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_torznab_test.py -v`
Expected: FAIL — `AttributeError: 'TorznabIndexer' object has no attribute 'test'`.

- [ ] **Step 3: Append the implementation**

Append this method inside the `TorznabIndexer` class in `torsearch/indexers/torznab.py` (after `search`):
```python
    async def test(self) -> tuple[bool, str]:
        params: dict[str, str] = {"t": "caps"}
        if self._auth == AuthMode.QUERY:
            params["apikey"] = self._api_key
        headers = self._build_headers()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(self._url, params=params, headers=headers)
            if response.status_code in (401, 403):
                return False, "Clé API refusée (401/403)."
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if root.tag != "caps":
                return False, "Réponse inattendue (pas un flux Torznab)."
            return True, "OK"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {exc}."
        except ET.ParseError:
            return False, "Réponse invalide (XML illisible)."
        finally:
            if owns_client:
                await client.aclose()
```

(No new imports needed — `httpx`, `AuthMode`, and `ET` are already imported in this module.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_torznab_test.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/indexers/torznab.py tests/test_torznab_test.py
git commit -m "feat: add Torznab connection test via t=caps"
```

---

## Task 5: Rebrancher l'app sur AppContext

Goal: `create_app(ctx)` ; `/search` & `/download` & `/trackers` lisent via `ctx` ; `main.build_app` construit le store + le contexte. La page `/trackers` reste fonctionnelle (elle sera retirée en Task 6).

**Files:**
- Create: `torsearch/web/templating.py`
- Modify: `torsearch/web/routes.py`, `torsearch/main.py`
- Modify (rewrite): `tests/test_web.py`, `tests/test_main.py`

- [ ] **Step 1: Rewrite the web tests (failing)**

Replace the entire contents of `tests/test_web.py` with:
```python
from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.models import Category, SearchResult
from torsearch.search.service import SearchService
from torsearch.web.routes import create_app


class FakeIndexer:
    def __init__(self, name, results=None):
        self.name = name
        self.enabled = True
        self._results = results or []

    async def search(self, query, category):
        return list(self._results)


class FakeTransmission:
    def __init__(self):
        self.added = []

    def add(self, download_url):
        self.added.append(download_url)
        return 7


class FakeContext:
    def __init__(self, search_service, transmission, config):
        self.search_service = search_service
        self.transmission = transmission
        self.config = config


def _make(results=None):
    service = SearchService([FakeIndexer("t1", results or [])])
    transmission = FakeTransmission()
    config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")])
    client = TestClient(create_app(FakeContext(service, transmission, config)))
    return client, transmission


def _movie():
    return SearchResult(
        title="Cool.Movie.2024", size=2147483648, seeders=99, leechers=3,
        source="t1", category=Category.MOVIES, download_url="magnet:?xt=urn:btih:ABC",
    )


def test_index_renders_search_form():
    client, _ = _make()
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'name="q"' in resp.text


def test_search_renders_result_rows():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "cool", "cat": "all"})
    assert resp.status_code == 200
    assert "Cool.Movie.2024" in resp.text
    assert "99" in resp.text


def test_search_empty_query_shows_placeholder():
    client, _ = _make([_movie()])
    resp = client.get("/search", params={"q": "   "})
    assert resp.status_code == 200
    assert "Aucun" in resp.text


def test_download_sends_to_transmission():
    client, transmission = _make()
    resp = client.post("/download", data={"download_url": "magnet:?xt=urn:btih:XYZ"})
    assert resp.status_code == 200
    assert transmission.added == ["magnet:?xt=urn:btih:XYZ"]
    assert "Transmission" in resp.text


def test_trackers_page_lists_indexer_names():
    client, _ = _make()
    resp = client.get("/trackers")
    assert resp.status_code == 200
    assert "t1" in resp.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: FAIL — `create_app()` still requires `(search_service, transmission)`, so passing a single `FakeContext` errors.

- [ ] **Step 3: Add shared templating module + rewrite routes**

`torsearch/web/templating.py`:
```python
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```

Replace the entire contents of `torsearch/web/routes.py` with:
```python
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.models import Category
from torsearch.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"categories": list(Category)})


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", cat: str = "all"):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    results = await ctx.search_service.search(q, category) if q.strip() else []
    return templates.TemplateResponse(request, "partials/results.html", {"results": results, "query": q})


@router.post("/download", response_class=HTMLResponse)
async def download(request: Request, download_url: str = Form(...)):
    ctx: AppContext = request.app.state.ctx
    try:
        torrent_id = ctx.transmission.add(download_url)
        message, ok = f"Ajoute a Transmission (#{torrent_id})", True
    except Exception as exc:
        message, ok = f"Erreur Transmission : {exc}", False
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})


@router.get("/trackers", response_class=HTMLResponse)
async def trackers(request: Request):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(request, "trackers.html", {"indexers": ctx.config.indexers})


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="TorSearch")
    app.state.ctx = ctx
    app.include_router(router)
    return app
```

- [ ] **Step 4: Run web tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Rewrite main wiring + its test (failing first)**

Replace the entire contents of `tests/test_main.py` with:
```python
from fastapi import FastAPI

from torsearch import main


def test_build_app_wires_context_and_bootstraps(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKER1_API_KEY", "secret")
    config = tmp_path / "config.yaml"
    config.write_text(
        "indexers:\n"
        "  - name: tracker1\n"
        "    type: torznab\n"
        "    url: https://tracker1.example/api\n"
        "    api_key: ${TRACKER1_API_KEY}\n"
        "    enabled: true\n"
    )
    settings = tmp_path / "data" / "settings.json"
    app = main.build_app(settings_path=str(settings), bootstrap_config_path=str(config))
    assert isinstance(app, FastAPI)
    assert [ix.name for ix in app.state.ctx.search_service.indexers] == ["tracker1"]
    assert settings.exists()
```

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `build_app` signature/behavior not updated yet.

- [ ] **Step 6: Update `torsearch/main.py`**

Replace the entire contents of `torsearch/main.py` with:
```python
from __future__ import annotations

import os

from fastapi import FastAPI

from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app

DEFAULT_SETTINGS_PATH = os.environ.get("TORSEARCH_SETTINGS", "data/settings.json")
DEFAULT_CONFIG_PATH = os.environ.get("TORSEARCH_CONFIG", "config.yaml")


def build_app(
    settings_path: str = DEFAULT_SETTINGS_PATH,
    bootstrap_config_path: str = DEFAULT_CONFIG_PATH,
) -> FastAPI:
    store = SettingsStore(settings_path, bootstrap_config_path=bootstrap_config_path)
    ctx = AppContext(store)
    return create_app(ctx)


def get_app() -> FastAPI:
    return build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — all tests (v1 tests + Tasks 1-4 + rewritten web/main). No failures.

- [ ] **Step 8: Commit**

```bash
git add torsearch/web/templating.py torsearch/web/routes.py torsearch/main.py tests/test_web.py tests/test_main.py
git commit -m "refactor: serve services through AppContext"
```

---

## Task 6: Page Réglages (lecture + réglages généraux)

Goal: page `/settings` affichant les réglages généraux (Transmission + recherche) et la liste des trackers ; `POST /settings/general` sauvegarde via `ctx`. La nav passe à « Réglages », l'ancienne page `/trackers` est retirée.

**Files:**
- Create: `torsearch/web/settings_routes.py`, `torsearch/web/templates/settings.html`, `torsearch/web/templates/partials/indexer_list.html`, `torsearch/web/templates/partials/indexer_row.html`
- Modify: `torsearch/web/routes.py` (include settings router, remove `/trackers`), `torsearch/web/templates/base.html` (nav)
- Delete: `torsearch/web/templates/trackers.html`
- Remove the `test_trackers_page_lists_indexer_names` test from `tests/test_web.py`
- Test: `tests/test_settings_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings_web.py`:
```python
from fastapi.testclient import TestClient

from torsearch.config import Config, IndexerConfig
from torsearch.context import AppContext
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    return TestClient(create_app(ctx)), ctx


def test_settings_page_renders_general_and_trackers(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="tracker1", url="https://tracker1.example/api", api_key="k")])
    client, _ = _client(tmp_path, cfg)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Transmission" in resp.text
    assert "tracker1" in resp.text
    assert 'name="timeout_seconds"' in resp.text


def test_general_update_persists_and_reloads(tmp_path):
    client, ctx = _client(tmp_path)
    resp = client.post("/settings/general", data={
        "host": "tr.local", "port": "9092", "username": "u", "password": "p",
        "https": "on", "timeout_seconds": "7",
    })
    assert resp.status_code == 200
    assert ctx.config.transmission.host == "tr.local"
    assert ctx.config.transmission.port == 9092
    assert ctx.config.transmission.https is True
    assert ctx.config.search.timeout_seconds == 7


def test_general_update_rejects_bad_port(tmp_path):
    client, ctx = _client(tmp_path)
    resp = client.post("/settings/general", data={
        "host": "h", "port": "abc", "timeout_seconds": "7",
    })
    assert resp.status_code == 200
    assert "Erreur" in resp.text
    assert ctx.config.transmission.host != "h"  # not saved
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_web.py -v`
Expected: FAIL — `404` for `/settings` (router not mounted) / `ModuleNotFoundError` for `settings_routes`.

- [ ] **Step 3: Create the templates**

`torsearch/web/templates/partials/indexer_row.html`:
```html
<form hx-post="/settings/indexers/{{ ix.name }}" hx-target="#indexer-list" hx-swap="outerHTML"
      class="flex flex-wrap items-end gap-2 border-b border-slate-800 py-3">
  <label class="text-xs text-slate-400">Nom<br>
    <input name="name" value="{{ ix.name }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
  <label class="text-xs text-slate-400">URL<br>
    <input name="url" value="{{ ix.url }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-72"></label>
  <label class="text-xs text-slate-400">Passkey<br>
    <input name="api_key" value="{{ ix.api_key }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
  <label class="text-xs text-slate-400">Auth<br>
    <select name="auth" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
      <option value="query" {% if ix.auth.value == 'query' %}selected{% endif %}>query</option>
      <option value="bearer" {% if ix.auth.value == 'bearer' %}selected{% endif %}>bearer</option>
    </select></label>
  <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-xs">Enregistrer</button>
  <button type="button" hx-post="/settings/indexers/{{ ix.name }}/toggle" hx-target="#indexer-list" hx-swap="outerHTML"
          class="rounded {% if ix.enabled %}bg-amber-600 hover:bg-amber-500{% else %}bg-slate-600 hover:bg-slate-500{% endif %} px-2 py-1 text-xs">
    {{ "Desactiver" if ix.enabled else "Activer" }}</button>
  <button type="button" hx-post="/settings/indexers/test" hx-include="closest form" hx-target="#toast"
          class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs">Tester</button>
  <button type="button" hx-post="/settings/indexers/{{ ix.name }}/delete" hx-target="#indexer-list" hx-swap="outerHTML"
          class="rounded bg-red-700 hover:bg-red-600 px-2 py-1 text-xs">Supprimer</button>
</form>
```

`torsearch/web/templates/partials/indexer_list.html`:
```html
<div id="indexer-list">
  {% if error %}<div class="mb-3 rounded bg-red-600 px-3 py-2 text-sm">{{ error }}</div>{% endif %}
  {% if notice %}<div class="mb-3 rounded bg-emerald-600 px-3 py-2 text-sm">{{ notice }}</div>{% endif %}
  {% for ix in indexers %}
    {% include "partials/indexer_row.html" %}
  {% else %}
    <p class="text-slate-400">Aucun tracker. Ajoute-en un ci-dessus.</p>
  {% endfor %}
</div>
```

`torsearch/web/templates/settings.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-lg font-semibold mb-6">Reglages</h1>

<section class="mb-10">
  <h2 class="font-semibold mb-2">Transmission &amp; recherche</h2>
  <form hx-post="/settings/general" hx-target="#toast" class="flex flex-wrap items-end gap-3">
    <label class="text-xs text-slate-400">Hote<br>
      <input name="host" value="{{ config.transmission.host }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400">Port<br>
      <input name="port" value="{{ config.transmission.port }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-24"></label>
    <label class="text-xs text-slate-400">Utilisateur<br>
      <input name="username" value="{{ config.transmission.username }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400">Mot de passe<br>
      <input name="password" type="password" value="{{ config.transmission.password }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400 flex items-center gap-1">
      <input type="checkbox" name="https" {% if config.transmission.https %}checked{% endif %}> https</label>
    <label class="text-xs text-slate-400">Timeout (s)<br>
      <input name="timeout_seconds" value="{{ config.search.timeout_seconds }}" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-24"></label>
    <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
  </form>
</section>

<section>
  <h2 class="font-semibold mb-2">Trackers</h2>
  <form hx-post="/settings/indexers" hx-target="#indexer-list" hx-swap="outerHTML"
        class="flex flex-wrap items-end gap-2 mb-4">
    <label class="text-xs text-slate-400">Nom<br>
      <input name="name" placeholder="ex: tracker1" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400">URL Torznab<br>
      <input name="url" placeholder="https://.../api" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-72"></label>
    <label class="text-xs text-slate-400">Passkey<br>
      <input name="api_key" class="rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <label class="text-xs text-slate-400">Auth<br>
      <select name="auth" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
        <option value="query">query</option><option value="bearer">bearer</option>
      </select></label>
    <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-sm">Ajouter</button>
  </form>
  {% include "partials/indexer_list.html" %}
</section>
{% endblock %}
```

- [ ] **Step 4: Create the settings router (general only for now)**

`torsearch/web/settings_routes.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import SearchConfig, TransmissionConfig
from torsearch.context import AppContext
from torsearch.settings.mutations import SettingsError, set_general
from torsearch.web.templating import templates

settings_router = APIRouter()


def _toast(request: Request, ok: bool, message: str):
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})


def _list(request: Request, ctx: AppContext, error: str | None = None, notice: str | None = None):
    return templates.TemplateResponse(
        request, "partials/indexer_list.html",
        {"indexers": ctx.config.indexers, "error": error, "notice": notice},
    )


@settings_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(
        request, "settings.html", {"config": ctx.config, "indexers": ctx.config.indexers}
    )


@settings_router.post("/settings/general", response_class=HTMLResponse)
async def update_general(
    request: Request,
    host: str = Form(...),
    port: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    https: str | None = Form(None),
    timeout_seconds: str = Form(...),
):
    ctx: AppContext = request.app.state.ctx
    try:
        transmission = TransmissionConfig(
            host=host, port=port, username=username, password=password, https=https is not None
        )
        search = SearchConfig(timeout_seconds=timeout_seconds)
        ctx.update_settings(set_general(ctx.config, transmission, search))
        return _toast(request, True, "Reglages enregistres.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
```

- [ ] **Step 5: Mount the router, drop `/trackers`, update nav, delete old template**

In `torsearch/web/routes.py`: add the import near the other imports —
```python
from torsearch.web.settings_routes import settings_router
```
remove the entire `@router.get("/trackers", ...)` handler function, and in `create_app` add after `app.include_router(router)`:
```python
    app.include_router(settings_router)
```

In `tests/test_web.py`, delete the `test_trackers_page_lists_indexer_names` function (the `/trackers` route no longer exists).

Delete the file `torsearch/web/templates/trackers.html`:
```bash
git rm torsearch/web/templates/trackers.html
```

In `torsearch/web/templates/base.html`, change the nav link:
```html
      <a href="/trackers" class="hover:text-emerald-400">Trackers</a>
```
to:
```html
      <a href="/settings" class="hover:text-emerald-400">Reglages</a>
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — `tests/test_settings_web.py` (3 tests) green, `tests/test_web.py` green without the trackers test, everything else green.

- [ ] **Step 7: Commit**

```bash
git add torsearch/web/settings_routes.py torsearch/web/templates/settings.html torsearch/web/templates/partials/indexer_list.html torsearch/web/templates/partials/indexer_row.html torsearch/web/routes.py torsearch/web/templates/base.html tests/test_settings_web.py tests/test_web.py
git rm torsearch/web/templates/trackers.html
git commit -m "feat: add settings page with general settings, replace trackers page"
```

---

## Task 7: CRUD trackers + bouton Tester

Goal: ajouter/modifier/supprimer/(dés)activer un tracker, et tester sa connexion, depuis la page Réglages.

**Files:**
- Modify: `torsearch/web/settings_routes.py` (add indexer routes)
- Test: `tests/test_settings_web.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_settings_web.py`:
```python
import httpx
import respx

from torsearch.config import IndexerConfig


def test_add_indexer_appears_in_list_and_config(tmp_path):
    client, ctx = _client(tmp_path)
    resp = client.post("/settings/indexers", data={
        "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert "tracker1" in resp.text
    assert [ix.name for ix in ctx.config.indexers] == ["tracker1"]


def test_add_indexer_duplicate_shows_error(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="tracker1", url="https://tracker1.example/api", api_key="k")])
    client, ctx = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers", data={
        "name": "tracker1", "url": "https://other/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert "existe" in resp.text  # error banner
    assert len(ctx.config.indexers) == 1


def test_update_indexer_changes_url_preserves_enabled(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://old/api", api_key="k", enabled=False)])
    client, ctx = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers/t", data={
        "name": "t", "url": "https://new/api", "api_key": "k", "auth": "query",
    })
    assert resp.status_code == 200
    assert ctx.config.indexers[0].url == "https://new/api"
    assert ctx.config.indexers[0].enabled is False  # preserved (not in form)


def test_toggle_indexer_flips_enabled(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://t/api", api_key="k", enabled=True)])
    client, ctx = _client(tmp_path, cfg)
    client.post("/settings/indexers/t/toggle")
    assert ctx.config.indexers[0].enabled is False


def test_delete_indexer_removes_it(tmp_path):
    cfg = Config(indexers=[IndexerConfig(name="t", url="https://t/api", api_key="k")])
    client, ctx = _client(tmp_path, cfg)
    resp = client.post("/settings/indexers/t/delete")
    assert resp.status_code == 200
    assert ctx.config.indexers == []


def test_test_indexer_returns_ok_toast(tmp_path):
    client, _ = _client(tmp_path)
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(
            return_value=httpx.Response(200, content=b'<?xml version="1.0"?><caps/>')
        )
        resp = client.post("/settings/indexers/test", data={
            "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "k", "auth": "query",
        })
    assert resp.status_code == 200
    assert "OK" in resp.text


def test_test_indexer_returns_error_toast_on_401(tmp_path):
    client, _ = _client(tmp_path)
    with respx.mock:
        respx.get("https://tracker1.example/api").mock(return_value=httpx.Response(401))
        resp = client.post("/settings/indexers/test", data={
            "name": "tracker1", "url": "https://tracker1.example/api", "api_key": "bad", "auth": "query",
        })
    assert resp.status_code == 200
    assert "refus" in resp.text.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_web.py -v`
Expected: FAIL — the indexer routes return 404 (not defined yet).

- [ ] **Step 3: Add the indexer routes**

Append to `torsearch/web/settings_routes.py`. First extend the imports at the top:
```python
from torsearch.config import IndexerConfig
from torsearch.indexers.torznab import TorznabIndexer
from torsearch.settings.mutations import (
    add_indexer,
    remove_indexer,
    set_indexer_enabled,
    update_indexer,
)
```
(keep the existing imports of `SearchConfig`, `TransmissionConfig`, `SettingsError`, `set_general`.)

Then append these handlers:
```python
@settings_router.post("/settings/indexers", response_class=HTMLResponse)
async def add_indexer_route(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    ctx: AppContext = request.app.state.ctx
    try:
        indexer = IndexerConfig(name=name, url=url, api_key=api_key, auth=auth, enabled=True)
        ctx.update_settings(add_indexer(ctx.config, indexer))
        return _list(request, ctx, notice=f"Tracker « {name} » ajoute.")
    except (ValidationError, SettingsError) as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/test", response_class=HTMLResponse)
async def test_indexer_route(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    try:
        indexer = TorznabIndexer(IndexerConfig(name=name, url=url, api_key=api_key, auth=auth))
    except ValidationError as exc:
        return _toast(request, False, f"Erreur : {exc}")
    ok, message = await indexer.test()
    return _toast(request, ok, f"{name} : {message}")


@settings_router.post("/settings/indexers/{name}", response_class=HTMLResponse)
async def update_indexer_route(
    request: Request,
    name: str,
    url: str = Form(...),
    api_key: str = Form(""),
    auth: str = Form("query"),
):
    ctx: AppContext = request.app.state.ctx
    form = await request.form()
    new_name = str(form.get("name", name))
    current = next((ix for ix in ctx.config.indexers if ix.name == name), None)
    enabled = current.enabled if current else True
    try:
        indexer = IndexerConfig(name=new_name, url=url, api_key=api_key, auth=auth, enabled=enabled)
        ctx.update_settings(update_indexer(ctx.config, name, indexer))
        return _list(request, ctx, notice="Tracker mis a jour.")
    except (ValidationError, SettingsError) as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/{name}/toggle", response_class=HTMLResponse)
async def toggle_indexer_route(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((ix for ix in ctx.config.indexers if ix.name == name), None)
    try:
        ctx.update_settings(set_indexer_enabled(ctx.config, name, not current.enabled if current else True))
        return _list(request, ctx)
    except SettingsError as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")


@settings_router.post("/settings/indexers/{name}/delete", response_class=HTMLResponse)
async def delete_indexer_route(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_indexer(ctx.config, name))
        return _list(request, ctx, notice=f"Tracker « {name} » supprime.")
    except SettingsError as exc:
        return _list(request, ctx, error=f"Erreur : {exc}")
```

> Route order matters: `/settings/indexers/test` is declared **before** `/settings/indexers/{name}` so that "test" is not captured as a `{name}` path parameter.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — the 7 new settings tests green, everything else green.

- [ ] **Step 5: Commit**

```bash
git add torsearch/web/settings_routes.py tests/test_settings_web.py
git commit -m "feat: add tracker CRUD and connection test from settings UI"
```

---

## Task 8: Packaging & docs

**Files:**
- Modify: `.gitignore`, `docker-compose.yml`, `config.example.yaml`, `README.md`

- [ ] **Step 1: Ignore the data directory**

In `.gitignore`, under the `# Secrets / config locale` section, add:
```
data/
```

- [ ] **Step 2: Mount the data volume in compose**

In `docker-compose.yml`, under the `torsearch` service, add to `volumes` and add an `environment` block:
```yaml
    volumes:
      - ./config:/config        # placer config.yaml dans ./config/ (amorcage initial)
      - ./data:/data            # settings.json persistant (gere par l'UI)
    environment:
      - TORSEARCH_SETTINGS=/data/settings.json
```
(Keep the existing `env_file: - .env` and `ports`.)

- [ ] **Step 3: Document the new flow**

In `README.md`, replace the `## Configuration` section body with:
```markdown
- Au **premier** demarrage, l'app lit `config.yaml` (amorcage) et ecrit `data/settings.json`.
- Ensuite, **toute la configuration se fait depuis la page Reglages** (http://localhost:8000/settings) :
  trackers, connexion Transmission, timeout. Chaque sauvegarde s'applique immediatement (pas de redemarrage).
- `data/settings.json` est la source de verite (gitignore). `config.yaml` ne sert qu'a l'amorcage initial
  et reste optionnel : sans lui, l'app demarre vide et tu ajoutes tout via l'UI.
- Bouton **Tester** sur chaque tracker pour verifier URL + passkey.
```

In `config.example.yaml`, add a leading comment line at the very top:
```yaml
# Fichier d'AMORCAGE uniquement (1er demarrage). Ensuite, edite la config via la page Reglages de l'UI.
# La source de verite runtime est data/settings.json (gere par l'app).
```

- [ ] **Step 4: Verify the full suite and a real startup**

Run:
```bash
.venv/bin/python -m pytest -v
.venv/bin/python -c "from torsearch.main import build_app; build_app(settings_path='/tmp/ts_settings.json', bootstrap_config_path='/does/not/exist'); print('factory OK (empty bootstrap)')"
```
Expected: all tests PASS; prints `factory OK (empty bootstrap)` (app builds even with no config.yaml).

- [ ] **Step 5: Commit**

```bash
git add .gitignore docker-compose.yml config.example.yaml README.md
git commit -m "chore: persist settings volume and document UI configuration"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. **Démarrage à blanc** : sans `config.yaml` ni `data/settings.json`, lancer
   `uvicorn torsearch.main:get_app --factory --reload`, ouvrir `/settings`, ajouter tracker1 puis tracker2
   (URL + passkey), cliquer **Tester** sur chacun → toast OK attendu.
2. **Hot-reload** : après ajout, faire une recherche immédiatement (sans redémarrer) et vérifier
   que les résultats des nouveaux trackers remontent.
3. **Persistance** : redémarrer l'app et vérifier que les trackers ajoutés sont toujours là
   (lecture de `data/settings.json`).
4. **Transmission** : régler la connexion dans l'UI, lancer un téléchargement, confirmer l'ajout.
