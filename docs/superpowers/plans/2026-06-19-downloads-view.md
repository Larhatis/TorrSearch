# F3 — Téléchargements en cours — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une page `/downloads` qui liste les torrents Transmission (auto-rafraîchie) avec pause / reprise / suppression.

**Architecture:** On étend `TransmissionClient` avec un modèle normalisé `TorrentInfo` et `list_torrents/pause/resume/remove`. Un nouveau `downloads_router` HTMX rend une page dont la liste se rafraîchit toutes les 3 s ; les actions appellent le client et re-rendent la liste. Tout passe par `ctx.transmission`.

**Tech Stack:** Python 3.12+ (3.14 local) · FastAPI · Pydantic v2 · transmission-rpc · Jinja2 + HTMX · pytest.

**Base :** branche `feat/downloads-view` (sur `feat/result-filters`). Commandes via `.venv/bin/python -m pytest ...`. Code existant : `torsearch/transmission/client.py` (`TransmissionClient` avec `__init__(config, client_factory=Client)`, `_get_client`, `add`), `torsearch/web/routes.py` (`create_app(ctx)` qui monte déjà `router` + `settings_router`, importe `templates` de `torsearch.web.templating`), `torsearch/web/templates/base.html` (nav). Starlette : `templates.TemplateResponse(request, "name.html", {ctx})`.

---

## File Structure

| Fichier | Action |
|---|---|
| `torsearch/transmission/client.py` | Modifier — `TorrentInfo` + `list_torrents`/`pause`/`resume`/`remove`. |
| `tests/test_transmission.py` | Modifier — tests des nouvelles méthodes. |
| `torsearch/web/downloads_routes.py` | Créer — `downloads_router`. |
| `torsearch/web/templates/downloads.html` | Créer. |
| `torsearch/web/templates/partials/downloads_list.html` | Créer. |
| `torsearch/web/routes.py` | Modifier — monter `downloads_router`. |
| `torsearch/web/templates/base.html` | Modifier — lien nav. |
| `tests/test_downloads_web.py` | Créer. |

---

## Task 1: Étendre TransmissionClient

**Files:**
- Modify: `torsearch/transmission/client.py`
- Test: `tests/test_transmission.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_transmission.py`)**

Append to `tests/test_transmission.py`:
```python
from torsearch.transmission.client import TorrentInfo


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


def test_list_torrents_maps_fields():
    infos = _client_with(FakeRpcFull()).list_torrents()
    assert [i.name for i in infos] == ["A", "B"]
    a = infos[0]
    assert isinstance(a, TorrentInfo)
    assert a.id == 1 and a.percent == 42.5 and a.status == "downloading"
    assert a.down_rate == 1000 and a.up_rate == 50 and a.size == 2000


def test_pause_calls_stop_torrent():
    rpc = FakeRpcFull()
    _client_with(rpc).pause(7)
    assert ("stop", 7) in rpc.calls


def test_resume_calls_start_torrent():
    rpc = FakeRpcFull()
    _client_with(rpc).resume(7)
    assert ("start", 7) in rpc.calls


def test_remove_calls_remove_torrent_without_data():
    rpc = FakeRpcFull()
    _client_with(rpc).remove(7)
    assert ("remove", 7, False) in rpc.calls
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_transmission.py -v`
Expected: FAIL — `ImportError: cannot import name 'TorrentInfo'` / `AttributeError: ... 'list_torrents'`.

- [ ] **Step 3: Replace `torsearch/transmission/client.py` with**

```python
from __future__ import annotations

from pydantic import BaseModel
from transmission_rpc import Client

from torsearch.config import TransmissionConfig


class TorrentInfo(BaseModel):
    id: int
    name: str
    percent: float
    status: str
    down_rate: int
    up_rate: int
    size: int


class TransmissionClient:
    def __init__(self, config: TransmissionConfig, client_factory=Client):
        self._config = config
        self._client_factory = client_factory
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory(
                protocol="https" if self._config.https else "http",
                host=self._config.host,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
            )
        return self._client

    def add(self, download_url: str) -> int:
        torrent = self._get_client().add_torrent(download_url)
        return torrent.id

    def list_torrents(self) -> list[TorrentInfo]:
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
            for t in self._get_client().get_torrents()
        ]

    def pause(self, torrent_id: int) -> None:
        self._get_client().stop_torrent(torrent_id)

    def resume(self, torrent_id: int) -> None:
        self._get_client().start_torrent(torrent_id)

    def remove(self, torrent_id: int) -> None:
        self._get_client().remove_torrent(torrent_id, delete_data=False)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_transmission.py -v`
Expected: PASS — the 4 new tests **and** the 3 pre-existing `add`/https/credentials tests.

- [ ] **Step 5: Commit**

```bash
git add torsearch/transmission/client.py tests/test_transmission.py
git commit -m "feat: add list/pause/resume/remove to transmission client"
```

---

## Task 2: Page /downloads (routes + templates)

**Files:**
- Create: `torsearch/web/downloads_routes.py`, `torsearch/web/templates/downloads.html`, `torsearch/web/templates/partials/downloads_list.html`
- Modify: `torsearch/web/routes.py` (mount router), `torsearch/web/templates/base.html` (nav)
- Test: `tests/test_downloads_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_downloads_web.py`:
```python
from fastapi.testclient import TestClient

from torsearch.config import Config
from torsearch.transmission.client import TorrentInfo
from torsearch.web.routes import create_app


class FakeTransmission:
    def __init__(self, torrents=None, fail=False):
        self._torrents = torrents or []
        self._fail = fail
        self.calls = []

    def list_torrents(self):
        if self._fail:
            raise RuntimeError("down")
        return self._torrents

    def pause(self, tid):
        self.calls.append(("pause", tid))

    def resume(self, tid):
        self.calls.append(("resume", tid))

    def remove(self, tid):
        self.calls.append(("remove", tid))


class FakeContext:
    def __init__(self, transmission):
        self.transmission = transmission
        self.search_service = None
        self.config = Config()


def _client(transmission):
    return TestClient(create_app(FakeContext(transmission)))


def _ti(**o):
    base = dict(id=1, name="ubuntu.iso", percent=50.0, status="downloading",
                down_rate=1024, up_rate=0, size=2_000_000_000)
    base.update(o)
    return TorrentInfo(**base)


def test_downloads_page_has_autorefresh_container():
    resp = _client(FakeTransmission()).get("/downloads")
    assert resp.status_code == 200
    assert 'id="downloads-list"' in resp.text
    assert "every 3s" in resp.text


def test_downloads_list_renders_torrents():
    resp = _client(FakeTransmission([_ti(name="MyShow.S01E01"), _ti(id=2, name="MyMovie")])).get("/downloads/list")
    assert resp.status_code == 200
    assert "MyShow.S01E01" in resp.text
    assert "MyMovie" in resp.text


def test_downloads_list_empty_shows_placeholder():
    resp = _client(FakeTransmission([])).get("/downloads/list")
    assert "Aucun" in resp.text


def test_downloads_list_shows_error_when_transmission_down():
    resp = _client(FakeTransmission(fail=True)).get("/downloads/list")
    assert resp.status_code == 200
    assert "injoignable" in resp.text.lower()


def test_pause_calls_transmission_and_rerenders():
    fake = FakeTransmission([_ti(id=5, name="X")])
    resp = _client(fake).post("/downloads/5/pause")
    assert resp.status_code == 200
    assert ("pause", 5) in fake.calls


def test_resume_calls_transmission():
    fake = FakeTransmission([_ti(id=5, name="X", status="stopped")])
    _client(fake).post("/downloads/5/resume")
    assert ("resume", 5) in fake.calls


def test_delete_calls_transmission():
    fake = FakeTransmission([_ti(id=5, name="X")])
    _client(fake).post("/downloads/5/delete")
    assert ("remove", 5) in fake.calls
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_downloads_web.py -v`
Expected: FAIL — `404` for `/downloads` (router not mounted) / `ModuleNotFoundError: torsearch.web.downloads_routes`.

- [ ] **Step 3: Create the templates**

`torsearch/web/templates/downloads.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-lg font-semibold mb-4">Telechargements</h1>
<div id="downloads-list" hx-get="/downloads/list" hx-trigger="load, every 3s" hx-swap="outerHTML"></div>
{% endblock %}
```

`torsearch/web/templates/partials/downloads_list.html`:
```html
<div id="downloads-list" hx-get="/downloads/list" hx-trigger="every 3s" hx-swap="outerHTML">
  {% if error %}<div class="rounded bg-red-600 px-3 py-2 text-sm mb-3">{{ error }}</div>{% endif %}
  {% if not torrents %}
    <p class="text-slate-400">Aucun telechargement en cours.</p>
  {% else %}
  <table class="w-full text-sm">
    <thead class="text-left text-slate-400 border-b border-slate-700">
      <tr>
        <th class="py-2">Nom</th><th class="text-right">Avancement</th><th>Statut</th>
        <th class="text-right">Down</th><th class="text-right">Up</th><th class="text-right">Taille</th><th></th>
      </tr>
    </thead>
    <tbody>
    {% for t in torrents %}
      <tr class="border-b border-slate-800">
        <td class="py-2 pr-3">{{ t.name }}</td>
        <td class="text-right">{{ t.percent | round(1) }} %</td>
        <td class="text-slate-400">{{ t.status }}</td>
        <td class="text-right whitespace-nowrap">{{ (t.down_rate / 1024) | round(0) | int }} Ko/s</td>
        <td class="text-right whitespace-nowrap">{{ (t.up_rate / 1024) | round(0) | int }} Ko/s</td>
        <td class="text-right whitespace-nowrap">{{ (t.size / 1073741824) | round(2) }} Go</td>
        <td class="text-right whitespace-nowrap">
          {% if t.status == 'stopped' %}
          <button hx-post="/downloads/{{ t.id }}/resume" hx-target="#downloads-list" hx-swap="outerHTML"
                  class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-xs">Reprendre</button>
          {% else %}
          <button hx-post="/downloads/{{ t.id }}/pause" hx-target="#downloads-list" hx-swap="outerHTML"
                  class="rounded bg-amber-600 hover:bg-amber-500 px-2 py-1 text-xs">Pause</button>
          {% endif %}
          <button hx-post="/downloads/{{ t.id }}/delete" hx-target="#downloads-list" hx-swap="outerHTML"
                  class="rounded bg-red-700 hover:bg-red-600 px-2 py-1 text-xs">Supprimer</button>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>
```

- [ ] **Step 4: Create the router**

`torsearch/web/downloads_routes.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.web.templating import templates

downloads_router = APIRouter()


def _render_list(request: Request, error: str | None = None):
    ctx: AppContext = request.app.state.ctx
    torrents = []
    if error is None:
        try:
            torrents = ctx.transmission.list_torrents()
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
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/pause", response_class=HTMLResponse)
async def pause(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.pause(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/resume", response_class=HTMLResponse)
async def resume(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.resume(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)


@downloads_router.post("/downloads/{torrent_id}/delete", response_class=HTMLResponse)
async def delete(request: Request, torrent_id: int):
    try:
        request.app.state.ctx.transmission.remove(torrent_id)
    except Exception as exc:
        return _render_list(request, error=f"Action impossible : {exc}")
    return _render_list(request)
```

- [ ] **Step 5: Mount the router + add nav link**

In `torsearch/web/routes.py`, add an import next to the other `torsearch.web.*` imports:
```python
from torsearch.web.downloads_routes import downloads_router
```
and inside `create_app`, after `app.include_router(settings_router)`, add:
```python
    app.include_router(downloads_router)
```

In `torsearch/web/templates/base.html`, add a nav link after the existing « Reglages » link:
```html
      <a href="/downloads" class="hover:text-emerald-400">Telechargements</a>
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — the 7 new downloads tests green, plus everything pre-existing (F1 + v1 + v1.1).

- [ ] **Step 7: Commit**

```bash
git add torsearch/web/downloads_routes.py torsearch/web/templates/downloads.html torsearch/web/templates/partials/downloads_list.html torsearch/web/routes.py torsearch/web/templates/base.html tests/test_downloads_web.py
git commit -m "feat: add downloads page with live Transmission status and controls"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. Avec un Transmission joignable contenant au moins un torrent, ouvrir `/downloads` → la liste
   apparaît et se met à jour toute seule (~3 s).
2. Tester **Pause** → le statut passe à `stopped` et le bouton devient **Reprendre** ; **Reprendre**
   relance ; **Supprimer** retire le torrent de la liste (sans effacer les données).
3. Couper Transmission → la zone liste affiche « Transmission injoignable… » sans planter la page.
