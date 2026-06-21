# Phase B — Bibliothèque Films (Radarr-lite) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une bibliothèque de films « voulus » (ajoutés depuis Découvrir) que le monitor auto-grabbe selon un profil de qualité global, en passant chaque film en « obtenu ».

**Architecture:** `WantedMovie` (modèle) + `MovieLibrary` (store JSON séparé, calqué sur `MonitorHistory`) + `LibraryConfig` (profil global dans settings) + `run_movie_cycle` (réutilise `select_new`/`apply`) branché dans `MonitorRunner._loop` ; pages `/library` + bouton « Ajouter » sur les cartes Découvrir ; mini-form profil dans Réglages.

**Tech Stack:** FastAPI/Starlette, Jinja2/HTMX/Tailwind CDN, pytest + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-20-movie-library-design.md`

---

## Structure des fichiers

- **Modifier** `torsearch/models.py` — `WantedMovie`.
- **Modifier** `torsearch/config.py` — `LibraryConfig` + champ `library` sur `Config`.
- **Créer** `torsearch/library/__init__.py` (vide), `torsearch/library/movies.py` — `MovieLibrary`.
- **Modifier** `torsearch/monitor/runner.py` — `run_movie_cycle` + `MonitorRunner` (param `library`, appel dans `_loop`).
- **Modifier** `torsearch/main.py`, `torsearch/web/routes.py` — câblage `library`.
- **Créer** `torsearch/web/library_routes.py`, `templates/library.html`, `templates/partials/library_list.html`.
- **Modifier** `templates/base.html` (nav), `templates/partials/media_results.html` (bouton Ajouter).
- **Modifier** `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `templates/settings.html` — profil.
- **Tests** : `test_models.py`, `test_config.py`, `test_movie_library.py`, `test_monitor_runner.py`, `test_library_web.py`.

---

## Task 1 : Modèle `WantedMovie`

**Files:** Modify `torsearch/models.py` ; Test `tests/test_models.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_models.py` :

```python
from datetime import datetime, timezone

from torsearch.models import WantedMovie


def test_wanted_movie_defaults_and_poster_url():
    m = WantedMovie(tmdb_id=1, title="Dune", year="2024", poster_path="/p.jpg",
                    added_at=datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert m.status == "wanted"
    assert m.grabbed_at is None
    assert m.poster_url == "https://image.tmdb.org/t/p/w342/p.jpg"
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_models.py -q -k wanted_movie`
Expected: FAIL — `ImportError: cannot import name 'WantedMovie'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/models.py`, ajouter l'import datetime en tête s'il manque (le fichier importe déjà `from datetime import datetime`), puis ajouter après `MediaResult` :

```python
class WantedMovie(BaseModel):
    tmdb_id: int
    title: str
    year: str | None = None
    poster_path: str | None = None
    status: str = "wanted"  # "wanted" | "grabbed"
    added_at: datetime
    grabbed_at: datetime | None = None
    grabbed_title: str | None = None

    @computed_field
    @property
    def poster_url(self) -> str | None:
        if not self.poster_path:
            return None
        return f"https://image.tmdb.org/t/p/w342{self.poster_path}"
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_models.py -q -k wanted_movie`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add torsearch/models.py tests/test_models.py
git commit -m "feat: add WantedMovie model"
```

---

## Task 2 : `LibraryConfig`

**Files:** Modify `torsearch/config.py` ; Test `tests/test_config.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_config.py` :

```python
def test_library_profile_defaults(tmp_path):
    from torsearch.config import load_config

    p = tmp_path / "c.yaml"
    p.write_text("{}\n")
    cfg = load_config(p)
    assert cfg.library.qualities == ["2160p", "1080p"]
    assert cfg.library.min_seeders == 1


def test_library_profile_loaded(tmp_path):
    from torsearch.config import load_config

    p = tmp_path / "c.yaml"
    p.write_text("library:\n  qualities: [1080p]\n  min_seeders: 5\n")
    cfg = load_config(p)
    assert cfg.library.qualities == ["1080p"]
    assert cfg.library.min_seeders == 5
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_config.py -q -k library_profile`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'library'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/config.py`, ajouter avant `class Config` :

```python
class LibraryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    qualities: list[str] = Field(default_factory=lambda: ["2160p", "1080p"])
    min_seeders: int = 1
```

Et dans `class Config`, après `metadata` :

```python
    library: LibraryConfig = Field(default_factory=LibraryConfig)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_config.py -q -k library_profile`
Expected: PASS (2 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add LibraryConfig global quality profile"
```

---

## Task 3 : Store `MovieLibrary`

**Files:** Create `torsearch/library/__init__.py`, `torsearch/library/movies.py` ; Test `tests/test_movie_library.py`

- [ ] **Step 1 : Test**

Créer `tests/test_movie_library.py` :

```python
from datetime import datetime, timezone

from torsearch.library.movies import MovieLibrary
from torsearch.models import WantedMovie

NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)


def _movie(tmdb_id=1, title="Dune"):
    return WantedMovie(tmdb_id=tmdb_id, title=title, year="2024", added_at=NOW)


def test_add_and_list_persists(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    assert lib.add(_movie()) is True
    assert [m.title for m in MovieLibrary(tmp_path / "lib.json").list()] == ["Dune"]


def test_add_dedupes_by_tmdb_id(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie())
    assert lib.add(_movie(title="Dune bis")) is False
    assert len(lib.list()) == 1


def test_remove(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie(1))
    lib.add(_movie(2, "Other"))
    lib.remove(1)
    assert [m.tmdb_id for m in lib.list()] == [2]


def test_wanted_excludes_grabbed_and_mark_grabbed(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(_movie(1))
    lib.mark_grabbed(1, "Dune.2024.1080p", NOW)
    assert lib.wanted() == []
    grabbed = lib.list()[0]
    assert grabbed.status == "grabbed"
    assert grabbed.grabbed_title == "Dune.2024.1080p"
    assert grabbed.grabbed_at == NOW
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_movie_library.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.library'`

- [ ] **Step 3 : Implémenter**

Créer `torsearch/library/__init__.py` (vide).

Créer `torsearch/library/movies.py` :

```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from torsearch.models import WantedMovie


class MovieLibrary:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[WantedMovie]:
        if not self._path.exists():
            return []
        return [WantedMovie.model_validate(item) for item in json.loads(self._path.read_text())]

    def _save(self, movies: list[WantedMovie]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([m.model_dump(mode="json") for m in movies], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[WantedMovie]:
        return self._load()

    def wanted(self) -> list[WantedMovie]:
        return [m for m in self._load() if m.status == "wanted"]

    def add(self, movie: WantedMovie) -> bool:
        movies = self._load()
        if any(m.tmdb_id == movie.tmdb_id for m in movies):
            return False
        movies.append(movie)
        self._save(movies)
        return True

    def remove(self, tmdb_id: int) -> None:
        self._save([m for m in self._load() if m.tmdb_id != tmdb_id])

    def mark_grabbed(self, tmdb_id: int, grabbed_title: str, at: datetime) -> None:
        movies = self._load()
        for i, m in enumerate(movies):
            if m.tmdb_id == tmdb_id:
                movies[i] = m.model_copy(
                    update={"status": "grabbed", "grabbed_title": grabbed_title, "grabbed_at": at}
                )
        self._save(movies)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_movie_library.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/library/__init__.py torsearch/library/movies.py tests/test_movie_library.py
git commit -m "feat: add MovieLibrary JSON store"
```

---

## Task 4 : `run_movie_cycle` + runner

**Files:** Modify `torsearch/monitor/runner.py` ; Test `tests/test_monitor_runner.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_monitor_runner.py` (les helpers `_r`, `FakeSearch`, `FakeTransmission` existent déjà en haut du fichier) :

```python
from datetime import datetime, timezone

from torsearch.config import LibraryConfig
from torsearch.library.movies import MovieLibrary
from torsearch.models import WantedMovie
from torsearch.monitor.runner import run_movie_cycle

NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)


def _lib(tmp_path):
    lib = MovieLibrary(tmp_path / "lib.json")
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=NOW))
    return lib


async def test_movie_cycle_grabs_and_marks(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    created = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="X")]), tr, history)
    assert tr.added == ["magnet:?xt=urn:btih:Dune.2024.1080p"]
    assert [r.kind for r in created] == ["grabbed"]
    assert lib.wanted() == []
    assert lib.list()[0].status == "grabbed"


async def test_movie_cycle_disabled_globally(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=False))
    out = await run_movie_cycle(cfg, _lib(tmp_path), FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_movie_cycle_respects_quality_profile(tmp_path):
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["2160p"], min_seeders=1))
    tr = FakeTransmission()
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", seeders=50, infohash="X")]),
                                tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []
    assert lib.wanted()  # toujours voulu


async def test_movie_cycle_skips_already_grabbed(tmp_path):
    lib = _lib(tmp_path)
    lib.mark_grabbed(1, "old", NOW)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    out = await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_movie_cycle_resilient_to_search_error(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=True))
    out = await run_movie_cycle(cfg, _lib(tmp_path), FakeSearch([], error=True),
                                FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_monitor_runner.py -q -k movie_cycle`
Expected: FAIL — `ImportError: cannot import name 'run_movie_cycle'`

- [ ] **Step 3 : Implémenter `run_movie_cycle` + runner**

Dans `torsearch/monitor/runner.py`, modifier l'import des modèles :

```python
from torsearch.models import Category, SearchResult
```

Ajouter la fonction après `run_cycle` :

```python
async def run_movie_cycle(config, library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    for movie in library.wanted():
        query = f"{movie.title} {movie.year or ''}".strip()
        try:
            results = await search_service.search(query, Category.MOVIES)
        except Exception as exc:
            logger.warning("Movie search '%s' failed: %s", movie.title, exc)
            continue
        filters = ResultFilters(
            min_seeders=profile.min_seeders, qualities=profile.qualities,
            sort="seeders", direction="desc",
        )
        pick = select_new(results, filters, set())
        if pick is None:
            continue
        try:
            transmission.add(pick.download_url)
        except Exception as exc:
            logger.warning("Movie grab '%s' failed: %s", movie.title, exc)
            continue
        now = datetime.now(timezone.utc)
        library.mark_grabbed(movie.tmdb_id, pick.title, now)
        record = MonitorRecord(
            search=f"{movie.title} ({movie.year})", title=pick.title, source=pick.source,
            infohash=pick.infohash, download_url=pick.download_url, kind="grabbed", at=now,
        )
        history.add(record)
        created.append(record)
        if notifier is not None:
            try:
                await notifier.notify(config.notifications, record)
            except Exception as exc:
                logger.warning("Movie notif '%s' failed: %s", movie.title, exc)
    return created
```

Modifier `MonitorRunner.__init__` pour accepter `library` :

```python
    def __init__(self, ctx, history, notifier=None, library=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
        self._library = library
        self._task = None
```

Dans `MonitorRunner._loop`, après l'appel à `run_cycle(...)` et avant le calcul de `interval`, ajouter :

```python
                await run_movie_cycle(
                    self._ctx.config, self._library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                )
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_monitor_runner.py -q`
Expected: PASS (anciens + 5 nouveaux `movie_cycle`)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/monitor/runner.py tests/test_monitor_runner.py
git commit -m "feat: auto-grab wanted movies in the monitor cycle"
```

---

## Task 5 : Câblage `library` (build_app + create_app)

**Files:** Modify `torsearch/main.py`, `torsearch/web/routes.py` ; Test `tests/test_main.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_main.py` (dans le test existant, après `assert app.state.history is not None`) :

```python
    assert app.state.library is not None
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_main.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'library'`

- [ ] **Step 3 : Câbler `create_app`**

Dans `torsearch/web/routes.py`, modifier la signature de `create_app` et poser l'état :

```python
def create_app(
    ctx: AppContext, history=None, monitor=None, auth: AuthSettings | None = None, library=None
) -> FastAPI:
```

Après `app.state.history = history`, ajouter :

```python
    app.state.library = library
```

- [ ] **Step 4 : Câbler `build_app`**

Dans `torsearch/main.py`, ajouter les imports :

```python
from torsearch.library.movies import MovieLibrary
```

Ajouter la constante de chemin après `DEFAULT_MONITOR_PATH` :

```python
DEFAULT_LIBRARY_PATH = os.environ.get("TORSEARCH_LIBRARY", "data/library.json")
```

Modifier `build_app` (signature + corps) :

```python
def build_app(
    settings_path: str = DEFAULT_SETTINGS_PATH,
    bootstrap_config_path: str = DEFAULT_CONFIG_PATH,
    monitor_path: str = DEFAULT_MONITOR_PATH,
    library_path: str = DEFAULT_LIBRARY_PATH,
) -> FastAPI:
    store = SettingsStore(settings_path, bootstrap_config_path=bootstrap_config_path)
    ctx = AppContext(store)
    history = MonitorHistory(monitor_path)
    library = MovieLibrary(library_path)
    monitor = MonitorRunner(ctx, history, library=library)
    return create_app(ctx, history=history, monitor=monitor, auth=AuthSettings.from_env(), library=library)
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_main.py -q`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add torsearch/main.py torsearch/web/routes.py tests/test_main.py
git commit -m "feat: wire MovieLibrary into app and monitor"
```

---

## Task 6 : Web — page Bibliothèque + bouton Ajouter + nav

**Files:** Create `torsearch/web/library_routes.py`, `templates/library.html`, `templates/partials/library_list.html` ; Modify `torsearch/web/routes.py`, `templates/base.html`, `templates/partials/media_results.html` ; Test `tests/test_library_web.py`

- [ ] **Step 1 : Test**

Créer `tests/test_library_web.py` :

```python
import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.models import MediaResult, WantedMovie
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)


class FakeTmdb:
    enabled = True

    async def search(self, query):
        return [MediaResult(tmdb_id=693134, media_type="movie", title="Dune", year="2024",
                            poster_path="/a.jpg")]


class FakeCtx:
    def __init__(self, monitor_on=False):
        self.tmdb = FakeTmdb()
        self.config = Config(monitor=MonitorConfig(enabled=monitor_on))


def _client(tmp_path, monitor_on=False):
    lib = MovieLibrary(tmp_path / "lib.json")
    return TestClient(create_app(FakeCtx(monitor_on), library=lib)), lib


def test_library_add_persists(tmp_path):
    client, lib = _client(tmp_path)
    resp = client.post("/library/add", data={"tmdb_id": "693134", "title": "Dune", "year": "2024", "poster_path": "/a.jpg"})
    assert resp.status_code == 200
    assert [m.tmdb_id for m in lib.list()] == [693134]


def test_library_page_lists_movies_with_status(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=1, title="Dune", year="2024", added_at=NOW))
    html = client.get("/library").text
    assert "Dune" in html
    assert "Voulu" in html


def test_library_page_warns_when_monitor_off(tmp_path):
    client, _ = _client(tmp_path, monitor_on=False)
    assert "surveillance" in client.get("/library").text.lower()


def test_library_remove(tmp_path):
    client, lib = _client(tmp_path)
    lib.add(WantedMovie(tmdb_id=1, title="Dune", added_at=NOW))
    client.post("/library/1/remove")
    assert lib.list() == []


def test_discover_movie_card_has_add_button(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover/search", params={"q": "dune"}).text
    assert 'hx-post="/library/add"' in html


def test_nav_marks_library_active(tmp_path):
    client, _ = _client(tmp_path)
    assert re.search(r'href="/library"[^>]*aria-current="page"', client.get("/library").text)
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_library_web.py -q`
Expected: FAIL — `404` / `create_app` n'inclut pas `library_router`

- [ ] **Step 3 : Créer `library_routes.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedMovie
from torsearch.web.templating import templates

library_router = APIRouter()


@library_router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    ctx = request.app.state.ctx
    library = request.app.state.library
    return templates.TemplateResponse(
        request, "library.html",
        {"movies": library.list(), "monitor_on": ctx.config.monitor.enabled},
    )


@library_router.post("/library/add", response_class=HTMLResponse)
async def library_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    library = request.app.state.library
    added = library.add(WantedMovie(
        tmdb_id=tmdb_id, title=title, year=year or None, poster_path=poster_path or None,
        status="wanted", added_at=datetime.now(timezone.utc),
    ))
    message = "Ajoute a la bibliotheque." if added else "Deja dans la bibliotheque."
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@library_router.post("/library/{tmdb_id}/remove", response_class=HTMLResponse)
async def library_remove(request: Request, tmdb_id: int):
    library = request.app.state.library
    library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/library_list.html", {"movies": library.list()})
```

- [ ] **Step 4 : Créer `templates/library.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-4 text-lg font-semibold">Bibliotheque</h1>
{% if not monitor_on %}
<div class="mb-5 rounded-lg border border-amber-600/40 bg-amber-600/10 px-4 py-3 text-sm">
  <i class="ti ti-alert-triangle text-amber-400"></i> La surveillance est desactivee : active-la dans <a href="/surveillance" class="underline text-amber-300 hover:text-amber-200">Surveillance</a> pour l'auto-grab des films voulus.
</div>
{% endif %}
{% include "partials/library_list.html" %}
{% endblock %}
```

- [ ] **Step 5 : Créer `templates/partials/library_list.html`**

```html
<div id="library-list">
{% if not movies %}
  <p class="text-slate-400">Aucun film dans la bibliotheque. Ajoute-en depuis <a href="/discover" class="underline hover:text-emerald-400">Decouvrir</a>.</p>
{% else %}
<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
  {% for m in movies %}
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
        {% if m.status == 'grabbed' %}
        <span class="rounded px-1.5 py-0.5 text-[10px] bg-emerald-500/15 text-emerald-300">Obtenu</span>
        {% else %}
        <span class="rounded px-1.5 py-0.5 text-[10px] bg-amber-500/15 text-amber-300">Voulu</span>
        {% endif %}
        {% if m.year %}<span class="text-[11px] text-slate-500">{{ m.year }}</span>{% endif %}
      </div>
      <div class="mt-1 truncate text-sm text-slate-100" title="{{ m.title }}">{{ m.title }}</div>
      <button hx-post="/library/{{ m.tmdb_id }}/remove" hx-target="#library-list" hx-swap="outerHTML"
              class="mt-2 flex w-full items-center justify-center gap-1 rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-red-400">
        <i class="ti ti-trash"></i> Retirer
      </button>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
</div>
```

- [ ] **Step 6 : Inclure `library_router` + nav**

Dans `torsearch/web/routes.py`, après `from torsearch.web.discover_routes import discover_router` :

```python
from torsearch.web.library_routes import library_router
```

Après `app.include_router(discover_router)` :

```python
    app.include_router(library_router)
```

Dans `torsearch/web/templates/base.html`, après le lien `href="/discover"` (Decouvrir), insérer :

```html
      <a href="/library" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path.startswith('/library') %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path.startswith('/library') %} aria-current="page"{% endif %}><i class="ti ti-bookmark"></i>Bibliotheque</a>
```

- [ ] **Step 7 : Bouton « Ajouter » sur les cartes film (Découvrir)**

Dans `torsearch/web/templates/partials/media_results.html`, juste après le bouton « Torrents » (avant la fermeture `</div>` de `p-2.5`), insérer :

```html
      {% if m.media_type == 'movie' %}
      <button hx-post="/library/add" hx-target="#toast"
              hx-vals='{{ {"tmdb_id": m.tmdb_id, "title": m.title, "year": (m.year or ""), "poster_path": (m.poster_path or "")} | tojson }}'
              class="mt-1.5 flex w-full items-center justify-center gap-1 rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:text-emerald-400">
        <i class="ti ti-bookmark-plus"></i> Bibliotheque
      </button>
      {% endif %}
```

- [ ] **Step 8 : Vérifier le succès**

Run: `uv run pytest tests/test_library_web.py -q`
Expected: PASS (6 tests)

- [ ] **Step 9 : Commit**

```bash
git add torsearch/web/library_routes.py torsearch/web/templates/library.html torsearch/web/templates/partials/library_list.html torsearch/web/routes.py torsearch/web/templates/base.html torsearch/web/templates/partials/media_results.html tests/test_library_web.py
git commit -m "feat: library page, add-to-library button, and nav entry"
```

---

## Task 7 : Profil de qualité dans Réglages

**Files:** Modify `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `templates/settings.html` ; Test `tests/test_library_web.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_library_web.py` :

```python
def test_update_library_profile(tmp_path):
    from torsearch.context import AppContext
    from torsearch.settings.store import SettingsStore

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx, library=MovieLibrary(tmp_path / "lib.json")))
    resp = client.post("/settings/library", data={"quality": ["1080p"], "min_seeders": "5"})
    assert resp.status_code == 200
    assert ctx.config.library.qualities == ["1080p"]
    assert ctx.config.library.min_seeders == 5
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_library_web.py -q -k update_library_profile`
Expected: FAIL — `404 Not Found` pour `/settings/library`

- [ ] **Step 3 : Mutation `set_library`**

Dans `torsearch/settings/mutations.py`, ajouter l'import `LibraryConfig` à la ligne d'import existante :

```python
from torsearch.config import Config, IndexerConfig, LibraryConfig, MonitorConfig, NotificationChannel, SavedSearch, SearchConfig, TransmissionConfig
```

Ajouter la fonction à la fin du fichier :

```python
def set_library(config: Config, library: LibraryConfig) -> Config:
    return config.model_copy(update={"library": library})
```

- [ ] **Step 4 : Route `POST /settings/library`**

Dans `torsearch/web/settings_routes.py`, ajouter `LibraryConfig` à l'import depuis `torsearch.config` et `set_library` à l'import depuis `torsearch.settings.mutations`. Puis ajouter la route à la fin du fichier :

```python
@settings_router.post("/settings/library", response_class=HTMLResponse)
async def update_library(
    request: Request,
    quality: list[str] = Form(default=[]),
    min_seeders: str = Form("1"),
):
    ctx: AppContext = request.app.state.ctx
    try:
        profile = LibraryConfig(
            qualities=[q for q in quality if q],
            min_seeders=int(min_seeders) if min_seeders.lstrip("-").isdigit() else 0,
        )
        ctx.update_settings(set_library(ctx.config, profile))
        return _toast(request, True, "Profil bibliotheque enregistre.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
```

(L'import devient : `from torsearch.config import IndexerConfig, LibraryConfig, NotificationChannel, SearchConfig, TransmissionConfig` et `from torsearch.settings.mutations import (..., set_general, set_indexer_enabled, set_library, update_indexer)`.)

- [ ] **Step 5 : Section Réglages**

Dans `torsearch/web/templates/settings.html`, avant la dernière ligne `{% endblock %}`, ajouter :

```html
<section class="mt-10">
  <h2 class="font-semibold mb-2">Bibliotheque (profil de qualite)</h2>
  <form hx-post="/settings/library" hx-target="#toast" class="flex flex-wrap items-end gap-4">
    <fieldset class="text-xs text-slate-400">
      <legend>Qualites recherchees</legend>
      <div class="mt-1 flex gap-2">
        {% for qv in ["2160p", "1080p", "720p", "480p"] %}
        <label class="flex items-center gap-1"><input type="checkbox" name="quality" value="{{ qv }}" {% if qv in config.library.qualities %}checked{% endif %}> {{ qv }}</label>
        {% endfor %}
      </div>
    </fieldset>
    <label class="text-xs text-slate-400">Seeders min<br>
      <input name="min_seeders" value="{{ config.library.min_seeders }}" class="mt-1 w-24 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
  </form>
</section>
```

- [ ] **Step 6 : Vérifier le succès**

Run: `uv run pytest tests/test_library_web.py -q`
Expected: PASS (7 tests)

- [ ] **Step 7 : Commit**

```bash
git add torsearch/settings/mutations.py torsearch/web/settings_routes.py torsearch/web/templates/settings.html tests/test_library_web.py
git commit -m "feat: edit global library quality profile in settings"
```

---

## Task 8 : Vérification finale

- [ ] **Step 1 : Toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante (185) + nouveaux tests (models, config, movie_library, monitor_runner, main, library_web), aucune régression.

- [ ] **Step 2 : Vérif visuelle (optionnel, manuel)**

Lancer l'app (avec clé TMDB + surveillance activée + un tracker), Découvrir → « Bibliotheque » sur un film → page `/library` (statut Voulu) → après un cycle monitor, statut Obtenu.

---

## Self-review (notes)

- **Couverture spec :** `WantedMovie` (T1), `LibraryConfig` (T2), `MovieLibrary` store (T3), `run_movie_cycle`+runner (T4), câblage build_app/create_app (T5), page `/library`+add+remove+nav+bouton Découvrir (T6), profil Réglages (T7), non-régression (T8). ✔
- **Cohérence des noms :** `WantedMovie(tmdb_id,title,year,poster_path,status,added_at,grabbed_at,grabbed_title)`, `LibraryConfig(qualities,min_seeders)`, `MovieLibrary.list/wanted/add/remove/mark_grabbed`, `run_movie_cycle(config,library,search_service,transmission,history,notifier)`, `set_library`, `app.state.library`, routes `/library` `/library/add` `/library/{tmdb_id}/remove` `/settings/library`, cible `#library-list`. ✔
- **Pas de placeholder :** code/markup/commandes exacts partout.
- **Note échappement :** bouton « Ajouter » utilise `hx-vals='… | tojson'` en guillemets simples (leçon Phase A).
