# Statuts de connexion dans Réglages — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher en tête de Réglages l'état des connexions (Transmission, Jellyfin, TMDB, chaque tracker), vérifié en parallèle à l'ouverture et après chaque enregistrement.

**Architecture:** Une méthode `test() -> (ok, message)` qui ne lève jamais, par client ; `torsearch/health.py` orchestre en parallèle avec un délai global ; une route HTMX `GET /settings/status` rend un partiel chargé en différé ; les enregistrements renvoient `HX-Trigger: settings-saved` pour rafraîchir le panneau.

**Tech Stack:** Python 3.12+, FastAPI, httpx, transmission-rpc, Jinja2 + HTMX, pytest (+ pytest-asyncio auto, respx).

**Spec :** `docs/superpowers/specs/2026-09-24-connection-status-design.md`

**Commandes :** `.venv/bin/pytest`, `.venv/bin/ruff check torsearch tests`, `.venv/bin/mypy` (pas `uv run`).

---

## Structure des fichiers

- **Modifier** `torsearch/transmission/client.py` — `test()`.
- **Modifier** `torsearch/jellyfin/client.py` — `test()`.
- **Modifier** `torsearch/metadata/tmdb.py` — `test()`.
- **Créer** `torsearch/health.py` — `ServiceStatus`, `check_all`.
- **Modifier** `torsearch/web/settings_routes.py` — route `/settings/status`, helper `_saved`.
- **Créer** `torsearch/web/templates/partials/status_panel.html` ; **modifier** `settings.html`.
- **Tests** : `tests/test_transmission.py`, `tests/test_jellyfin.py`, `tests/test_tmdb.py`, `tests/test_health.py` (nouveau), `tests/test_settings_web.py`.

---

## Task 1 : `TransmissionClient.test()`

**Files:** Modify `torsearch/transmission/client.py` ; Test `tests/test_transmission.py`

- [ ] **Step 1 : Tests** — ajouter à la fin de `tests/test_transmission.py` :

```python
class FakeRpcSession(FakeRpcFull):
    def get_session(self):
        return SimpleNamespace(version="4.0.6 (38c164933e)")

    def session_stats(self):
        return SimpleNamespace(torrent_count=12)


async def test_test_reports_version_and_torrent_count():
    assert await _client_with(FakeRpcSession()).test() == (True, "v4.0.6 · 12 torrents")


async def test_test_never_raises_and_masks_credentials():
    def factory(**kwargs):
        raise RuntimeError("Invalid URL 'http://u:TR-SECRET@:9091/transmission/rpc'")

    ok, message = await TransmissionClient(TransmissionConfig(), client_factory=factory).test()
    assert ok is False
    assert "TR-SECRET" not in message
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_transmission.py -q -k "test_test"` → FAIL (`AttributeError: ... has no attribute 'test'`).

- [ ] **Step 3 : Implémenter** — dans `torsearch/transmission/client.py`, ajouter l'import `from torsearch.redact import redact` (après `from torsearch.config import TransmissionConfig`) et, à la fin de la classe :

```python
    async def test(self) -> tuple[bool, str]:
        """Connection check for the status panel: never raises, never echoes credentials."""
        try:
            version, count = await self._run(
                lambda c: (c.get_session().version, c.session_stats().torrent_count)
            )
        except Exception as exc:
            return False, redact(str(exc))
        label = str(version).split()[0] if version else "?"
        return True, f"v{label} · {count} torrent{'s' if count != 1 else ''}"
```

- [ ] **Step 4 :** `.venv/bin/pytest tests/test_transmission.py -q` → PASS.
- [ ] **Step 5 : Commit** — `feat(transmission): test de connexion (version, nombre de torrents)`.

---

## Task 2 : `JellyfinClient.test()`

**Files:** Modify `torsearch/jellyfin/client.py` ; Test `tests/test_jellyfin.py`

- [ ] **Step 1 : Tests** — ajouter à la fin de `tests/test_jellyfin.py` :

```python
async def test_test_reports_server_name_and_version():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="K"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(
            return_value=httpx.Response(200, json={"ServerName": "omvnas", "Version": "10.10.3"}))
        assert await client.test() == (True, "omvnas · Jellyfin 10.10.3")


async def test_test_rejected_key():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="BAD"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(return_value=httpx.Response(401))
        ok, message = await client.test()
    assert ok is False and "refusée" in message


async def test_test_error_never_echoes_the_key():
    client = JellyfinClient(JellyfinConfig(url="http://jelly", api_key="JF-SECRET"))
    with respx.mock:
        respx.get("http://jelly/System/Info").mock(return_value=httpx.Response(500))
        ok, message = await client.test()
    assert ok is False
    assert "500" in message and "JF-SECRET" not in message
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_jellyfin.py -q -k "test_test"` → FAIL (pas de méthode `test`).

- [ ] **Step 3 : Implémenter** — dans `torsearch/jellyfin/client.py`, ajouter l'import `from torsearch.redact import redact` (après `from torsearch.config import JellyfinConfig`) et, à la fin de la classe :

```python
    async def test(self) -> tuple[bool, str]:
        """Connection check for the status panel: never raises, never echoes the key."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(f"{self._url}/System/Info", params={"api_key": self._api_key})
            if response.status_code in (401, 403):
                return False, "Clé API refusée (401/403)."
            response.raise_for_status()
            info = response.json()
            return True, f"{info.get('ServerName', '?')} · Jellyfin {info.get('Version', '?')}"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.HTTPStatusError as exc:
            return False, f"Erreur HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {redact(str(exc))}."
        except ValueError:
            return False, "Réponse inattendue (pas un serveur Jellyfin ?)."
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4 :** `.venv/bin/pytest tests/test_jellyfin.py -q` → PASS.
- [ ] **Step 5 : Commit** — `feat(jellyfin): test de connexion (nom du serveur, version)`.

---

## Task 3 : `TmdbClient.test()`

**Files:** Modify `torsearch/metadata/tmdb.py` ; Test `tests/test_tmdb.py`

- [ ] **Step 1 : Tests** — ajouter à la fin de `tests/test_tmdb.py` :

```python
async def test_test_ok_with_valid_key():
    from torsearch.config import MetadataConfig
    from torsearch.metadata.tmdb import TmdbClient

    with respx.mock:
        respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(200, json={}))
        assert await TmdbClient(MetadataConfig(tmdb_api_key="k")).test() == (True, "OK")


async def test_test_rejected_key_never_echoed():
    from torsearch.config import MetadataConfig
    from torsearch.metadata.tmdb import TmdbClient

    with respx.mock:
        respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(401))
        ok, message = await TmdbClient(MetadataConfig(tmdb_api_key="TMDB-SECRET")).test()
    assert ok is False and "refusée" in message and "TMDB-SECRET" not in message
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_tmdb.py -q -k "test_test"` → FAIL.

- [ ] **Step 3 : Implémenter** — dans `torsearch/metadata/tmdb.py`, ajouter `_CONFIG_URL = "https://api.themoviedb.org/3/configuration"` après `_TV_URL`, l'import `from torsearch.redact import redact` (après `from torsearch.models import MediaResult`) et, dans la classe (après `trending`) :

```python
    async def test(self) -> tuple[bool, str]:
        """Key check for the status panel: never raises, never echoes the key."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(_CONFIG_URL, params={"api_key": self._api_key})
            if response.status_code == 401:
                return False, "Clé API refusée (401)."
            response.raise_for_status()
            return True, "OK"
        except httpx.TimeoutException:
            return False, "Pas de réponse (timeout)."
        except httpx.HTTPStatusError as exc:
            return False, f"Erreur HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Erreur réseau : {redact(str(exc))}."
        finally:
            if owns_client:
                await client.aclose()
```

- [ ] **Step 4 :** `.venv/bin/pytest tests/test_tmdb.py -q` → PASS.
- [ ] **Step 5 : Commit** — `feat(tmdb): test de la clé API`.

---

## Task 4 : `torsearch/health.py`

**Files:** Create `torsearch/health.py` ; Test `tests/test_health.py`

- [ ] **Step 1 : Tests** — créer `tests/test_health.py` :

```python
import asyncio

import httpx
import respx

from torsearch.config import Config, IndexerConfig, MetadataConfig, NotificationChannel
from torsearch.health import check_all


class _Service:
    def __init__(self, result=(True, "OK"), enabled=True, delay=0.0, error=None):
        self.enabled = enabled
        self._result, self._delay, self._error = result, delay, error

    async def test(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._result


class _Ctx:
    def __init__(self, config, transmission, jellyfin, tmdb):
        self.config, self.transmission, self.jellyfin, self.tmdb = config, transmission, jellyfin, tmdb


async def test_statuses_in_display_order_with_states():
    cfg = Config(
        metadata=MetadataConfig(tmdb_api_key="k"),
        indexers=[IndexerConfig(name="t1", url="https://t1.example/api", api_key="k"),
                  IndexerConfig(name="t2", url="https://t2.example/api", api_key="k", enabled=False)],
        notifications=[NotificationChannel(name="d", type="discord", url="https://x")],
    )
    ctx = _Ctx(cfg, _Service((True, "v4.0.6 · 3 torrents")), _Service((False, "Clé API refusée (401/403).")),
               _Service((True, "OK")))
    with respx.mock:
        respx.get("https://t1.example/api").mock(return_value=httpx.Response(200, content=b"<caps/>"))
        statuses = await check_all(ctx)
    assert [(s.name, s.state) for s in statuses] == [
        ("Transmission", "ok"), ("Jellyfin", "error"), ("TMDB", "ok"),
        ("t1", "ok"), ("t2", "off"), ("Notifications", "off"),
    ]
    assert statuses[0].message == "OK · v4.0.6 · 3 torrents"
    assert statuses[2].message == "OK"
    assert "test manuel" in statuses[5].message


async def test_unconfigured_services_are_off():
    ctx = _Ctx(Config(), _Service(), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx)
    assert [(s.name, s.state, s.message) for s in statuses[1:]] == [
        ("Jellyfin", "off", "Non configuré"), ("TMDB", "off", "Non configuré"),
    ]


async def test_tmdb_key_from_environment_is_flagged():
    ctx = _Ctx(Config(), _Service(), _Service(enabled=False), _Service((True, "OK")))  # no stored key
    statuses = await check_all(ctx)
    assert statuses[2].message == "OK · via TMDB_API_KEY"


async def test_a_hanging_service_times_out():
    ctx = _Ctx(Config(), _Service(delay=1.0), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx, timeout=0.05)
    assert (statuses[0].state, statuses[0].message) == ("error", "Pas de réponse (délai dépassé).")


async def test_an_unexpected_exception_is_masked():
    boom = RuntimeError("Invalid URL 'http://u:TR-SECRET@:9091/transmission/rpc'")
    ctx = _Ctx(Config(), _Service(error=boom), _Service(enabled=False), _Service(enabled=False))
    statuses = await check_all(ctx)
    assert statuses[0].state == "error" and "TR-SECRET" not in statuses[0].message
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_health.py -q` → FAIL (`ModuleNotFoundError: torsearch.health`).

- [ ] **Step 3 : Implémenter** — créer `torsearch/health.py` :

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Literal

from pydantic import BaseModel

from torsearch.indexers.torznab import TorznabIndexer
from torsearch.redact import redact


class ServiceStatus(BaseModel):
    name: str
    state: Literal["ok", "error", "off"]
    message: str


async def _probe(name: str, check: Awaitable[tuple[bool, str]], timeout: float) -> ServiceStatus:
    """Run one ``test()``; a slow or broken service never breaks the panel."""
    try:
        ok, detail = await asyncio.wait_for(check, timeout)
    except TimeoutError:
        return ServiceStatus(name=name, state="error", message="Pas de réponse (délai dépassé).")
    except Exception as exc:
        return ServiceStatus(name=name, state="error", message=redact(str(exc)))
    if not ok:
        return ServiceStatus(name=name, state="error", message=detail)
    return ServiceStatus(name=name, state="ok", message="OK" if detail in ("", "OK") else f"OK · {detail}")


async def _fixed(status: ServiceStatus) -> ServiceStatus:
    return status


async def _tmdb_test(ctx) -> tuple[bool, str]:
    ok, detail = await ctx.tmdb.test()
    if ok and not ctx.config.metadata.tmdb_api_key:
        return ok, "via TMDB_API_KEY"  # stored key empty: the environment fallback is in use
    return ok, detail


async def check_all(ctx, timeout: float = 12.0) -> list[ServiceStatus]:
    """Check every external service in parallel; statuses come back in display order."""
    config = ctx.config
    off = "Non configuré"
    checks: list[Awaitable[ServiceStatus]] = [
        _probe("Transmission", ctx.transmission.test(), timeout),
        _probe("Jellyfin", ctx.jellyfin.test(), timeout) if ctx.jellyfin.enabled
        else _fixed(ServiceStatus(name="Jellyfin", state="off", message=off)),
        _probe("TMDB", _tmdb_test(ctx), timeout) if ctx.tmdb.enabled
        else _fixed(ServiceStatus(name="TMDB", state="off", message=off)),
    ]
    for ix in config.indexers:
        if ix.enabled:
            indexer = TorznabIndexer(ix, timeout=config.search.timeout_seconds)
            checks.append(_probe(ix.name, indexer.test(), timeout))
        else:
            checks.append(_fixed(ServiceStatus(name=ix.name, state="off", message="Désactivé")))
    if config.notifications:
        n = len(config.notifications)
        label = f"{n} canal{'aux' if n > 1 else ''} · test manuel dans la section Notifications"
        checks.append(_fixed(ServiceStatus(name="Notifications", state="off", message=label)))
    return list(await asyncio.gather(*checks))
```

- [ ] **Step 4 :** `.venv/bin/pytest tests/test_health.py -q && .venv/bin/mypy` → PASS / Success.
- [ ] **Step 5 : Commit** — `feat: orchestration des tests de connexion (torsearch/health.py)`.

---

## Task 5 : Panneau dans Réglages

**Files:** Modify `torsearch/web/settings_routes.py`, `torsearch/web/templates/settings.html` ; Create `torsearch/web/templates/partials/status_panel.html` ; Test `tests/test_settings_web.py`

- [ ] **Step 1 : Tests** — ajouter à la fin de `tests/test_settings_web.py` :

```python
def test_settings_page_lazy_loads_the_status_panel(tmp_path):
    client, _, _ = _client(tmp_path)
    html = client.get("/settings").text
    assert 'id="status-panel"' in html
    assert 'hx-get="/settings/status"' in html
    assert "settings-saved from:body" in html


def test_status_route_renders_one_row_per_service(tmp_path, monkeypatch):
    from torsearch.health import ServiceStatus
    from torsearch.web import settings_routes

    async def fake_check_all(ctx):
        return [ServiceStatus(name="Transmission", state="ok", message="OK · v4.0.6 · 3 torrents"),
                ServiceStatus(name="Jellyfin", state="off", message="Non configuré"),
                ServiceStatus(name="t1", state="error", message="Clé API refusée (401/403).")]

    monkeypatch.setattr(settings_routes, "check_all", fake_check_all)
    client, _, _ = _client(tmp_path)
    html = client.get("/settings/status").text
    assert html.count("data-state=") == 3
    assert 'data-state="ok"' in html and 'data-state="off"' in html and 'data-state="error"' in html
    assert "v4.0.6" in html and "Reverifier" in html
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_settings_web.py -q -k "status"` → FAIL.

- [ ] **Step 3 : Route** — dans `torsearch/web/settings_routes.py`, ajouter l'import `from torsearch.health import check_all` (après `from torsearch.context import AppContext`) et, après `settings_page` :

```python
@settings_router.get("/settings/status", response_class=HTMLResponse)
async def settings_status(request: Request):
    ctx: AppContext = request.app.state.ctx
    statuses = await check_all(ctx)
    return templates.TemplateResponse(request, "partials/status_panel.html", {"statuses": statuses})
```

- [ ] **Step 4 : Partiel** — créer `torsearch/web/templates/partials/status_panel.html` :

```html
{% set dot = {'ok': 'bg-green-500', 'error': 'bg-red-500', 'off': 'bg-slate-500'} %}
{% set txt = {'ok': 'text-green-300', 'error': 'text-red-300', 'off': 'text-slate-500'} %}
<div class="mb-4 flex items-center gap-2 border-b border-slate-700/70 pb-3">
  <i class="ti ti-heartbeat text-slate-500"></i>
  <h2 class="text-sm font-semibold text-white">Etat des connexions</h2>
  <button type="button" hx-get="/settings/status" hx-target="#status-panel"
          class="ml-auto flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:text-emerald-400">
    <i class="ti ti-refresh"></i> Reverifier</button>
</div>
<ul class="space-y-1.5 text-sm">
  {% for s in statuses %}
  <li data-state="{{ s.state }}" class="flex items-center gap-3">
    <span class="h-2 w-2 shrink-0 rounded-full {{ dot[s.state] }}"></span>
    <span class="w-32 shrink-0 truncate text-slate-200">{{ s.name }}</span>
    <span class="min-w-0 truncate {{ txt[s.state] }}" title="{{ s.message }}">{{ s.message }}</span>
  </li>
  {% endfor %}
</ul>
```

- [ ] **Step 5 : Conteneur** — dans `settings.html`, juste après `<div class="space-y-5">`, insérer :

```html
<section id="status-panel" class="rounded-xl border border-slate-700 bg-slate-800/40 p-5"
         hx-get="/settings/status" hx-trigger="load, settings-saved from:body">
  <p class="text-xs text-slate-500"><i class="ti ti-loader"></i> Verification des connexions...</p>
</section>
```

- [ ] **Step 6 :** `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests` → PASS.
- [ ] **Step 7 : Commit** — `feat(settings): panneau « État des connexions »`.

---

## Task 6 : Rafraîchir le panneau après un enregistrement

**Files:** Modify `torsearch/web/settings_routes.py` ; Test `tests/test_settings_web.py`

- [ ] **Step 1 : Tests** — ajouter :

```python
def test_saving_connection_settings_refreshes_the_status_panel(tmp_path):
    client, _, _ = _client(tmp_path)
    responses = [
        client.post("/settings/general", data={"host": "h", "port": "9091", "password": "p", "timeout_seconds": "10"}),
        client.post("/settings/jellyfin", data={"url": "http://jelly", "api_key": "K"}),
        client.post("/settings/metadata", data={"tmdb_api_key": "k"}),
        client.post("/settings/indexers", data={"name": "t", "url": "https://t/api", "api_key": "k", "auth": "query"}),
        client.post("/settings/indexers/t/toggle"),
        client.post("/settings/indexers/t/delete"),
    ]
    for resp in responses:
        assert resp.headers.get("HX-Trigger") == "settings-saved"


def test_failed_save_does_not_refresh_the_status_panel(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.post("/settings/general", data={"host": "h", "port": "abc", "timeout_seconds": "10"})
    assert "HX-Trigger" not in resp.headers
```

- [ ] **Step 2 :** `.venv/bin/pytest tests/test_settings_web.py -q -k "refresh"` → FAIL.

- [ ] **Step 3 : Implémenter** — dans `torsearch/web/settings_routes.py`, ajouter après `_list` :

```python
def _saved(response):
    """A connection setting changed: the status panel re-checks (HTMX event)."""
    response.headers["HX-Trigger"] = "settings-saved"
    return response
```

puis envelopper par `_saved(...)` les retours de succès de : `update_general` (« Reglages enregistres. »), `update_jellyfin`, `update_metadata`, `add_indexer_route`, `update_indexer_route`, `toggle_indexer_route` (le `return _list(request, ctx)` du `try`) et `delete_indexer_route`. Exemple : `return _saved(_toast(request, True, "Jellyfin enregistre."))`.

- [ ] **Step 4 :** `.venv/bin/pytest -q && .venv/bin/ruff check torsearch tests && .venv/bin/mypy` → PASS.
- [ ] **Step 5 : Commit** — `feat(settings): le panneau d'état se rafraîchit après chaque enregistrement`.

---

## Task 7 : Vérification finale, revue, PR

- [ ] ruff, mypy, pytest verts ; contrôle navigateur (`/settings` : panneau chargé, pastilles cohérentes avec la config locale, « Reverifier » fonctionne, enregistrer Jellyfin relance le panneau ; console sans erreur).
- [ ] Revue indépendante (agent code-reviewer) sur la plage `origin/main..HEAD` ; corriger les points importants.
- [ ] Pousser la branche `claude/connection-status`, ouvrir la PR « Statuts de connexion dans Réglages » (corps terminé par la ligne d'attribution Claude Code).
