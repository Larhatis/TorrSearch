# Phase C — Bibliothèque Séries (Sonarr-lite) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suivre des séries ajoutées depuis Découvrir : parser les identifiants d'épisode des torrents et auto-grabber chaque nouvel épisode (et packs de saison) via le monitor.

**Architecture:** `parse_episodes` (parser TV pur) + `WantedSeries` (modèle) + `SeriesLibrary` (store JSON, calqué sur `MovieLibrary`) + `run_series_cycle` (grab multiple par cycle, réutilise `apply` + le profil global `LibraryConfig`) branché dans `MonitorRunner._loop` ; page Bibliothèque à deux sections (Films & Séries), bouton « Suivre » sur les cartes série de Découvrir.

**Tech Stack:** FastAPI/Starlette, Jinja2/HTMX/Tailwind CDN, pytest + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-21-series-library-design.md`

---

## Structure des fichiers

- **Créer** `torsearch/library/episodes.py` — `parse_episodes`.
- **Modifier** `torsearch/models.py` — `WantedSeries`.
- **Créer** `torsearch/library/series.py` — `SeriesLibrary`.
- **Modifier** `torsearch/monitor/runner.py` — `run_series_cycle` + `MonitorRunner` (param `series_library`).
- **Modifier** `torsearch/main.py`, `torsearch/web/routes.py` — câblage `series_library`.
- **Créer** `torsearch/web/series_routes.py`, `templates/partials/series_list.html`.
- **Modifier** `torsearch/web/library_routes.py` (page lit aussi les séries), `templates/library.html` (2 sections), `templates/partials/media_results.html` (bouton Suivre).
- **Tests** : `test_episode_parser.py`, `test_series_library.py`, `test_models.py`, `test_monitor_runner.py`, `test_main.py`, `test_series_web.py`.

---

## Task 1 : Parser TV `parse_episodes`

**Files:** Create `torsearch/library/episodes.py` ; Test `tests/test_episode_parser.py`

- [ ] **Step 1 : Tests**

Créer `tests/test_episode_parser.py` :

```python
from torsearch.library.episodes import parse_episodes


def test_single_episode():
    assert parse_episodes("Show.S01E01.1080p.WEB") == {"S01E01"}


def test_multi_episode_concat():
    assert parse_episodes("Show.S02E05E06.1080p") == {"S02E05", "S02E06"}


def test_multi_episode_dash():
    assert parse_episodes("Show.S02E05-E06.x265") == {"S02E05", "S02E06"}


def test_case_insensitive_and_zero_pad():
    assert parse_episodes("show.s1e5.hdtv") == {"S01E05"}


def test_season_pack_sxx():
    assert parse_episodes("Show.S02.COMPLETE.1080p") == {"S02"}


def test_season_pack_word_en():
    assert parse_episodes("Show.Season.3.1080p") == {"S03"}


def test_season_pack_word_fr():
    assert parse_episodes("Show.Saison.1.FRENCH") == {"S01"}


def test_unparsable_returns_empty():
    assert parse_episodes("Show.2024.1080p.WEB") == set()
    assert parse_episodes("Random.Movie.2160p.BluRay") == set()
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_episode_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.library.episodes'`

- [ ] **Step 3 : Implémenter**

Créer `torsearch/library/episodes.py` :

```python
from __future__ import annotations

import re

_EP_RE = re.compile(r"s(\d{1,2})((?:[ ._-]*e\d{1,2})+)", re.IGNORECASE)
_E_NUM_RE = re.compile(r"e(\d{1,2})", re.IGNORECASE)
_SEASON_RE = re.compile(
    r"(?:s(\d{1,2})\b|season[ ._-]*(\d{1,2})|saison[ ._-]*(\d{1,2}))", re.IGNORECASE
)


def parse_episodes(title: str) -> set[str]:
    keys: set[str] = set()
    for m in _EP_RE.finditer(title):
        season = int(m.group(1))
        for em in _E_NUM_RE.finditer(m.group(2)):
            keys.add(f"S{season:02d}E{int(em.group(1)):02d}")
    if keys:
        return keys
    sm = _SEASON_RE.search(title)
    if sm:
        season = int(next(g for g in sm.groups() if g))
        return {f"S{season:02d}"}
    return set()
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_episode_parser.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/library/episodes.py tests/test_episode_parser.py
git commit -m "feat: add TV episode/season parser"
```

---

## Task 2 : Modèle `WantedSeries`

**Files:** Modify `torsearch/models.py` ; Test `tests/test_models.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_models.py` :

```python
from torsearch.models import WantedSeries


def test_wanted_series_defaults_and_poster_url():
    s = WantedSeries(tmdb_id=1, title="Show", year="2024", poster_path="/s.jpg",
                     added_at=datetime(2026, 6, 21, tzinfo=timezone.utc))
    assert s.grabbed == []
    assert s.poster_url == "https://image.tmdb.org/t/p/w342/s.jpg"
```

(`datetime`/`timezone` sont déjà importés en bas de `tests/test_models.py` via les tests Phase B.)

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_models.py -q -k wanted_series`
Expected: FAIL — `ImportError: cannot import name 'WantedSeries'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/models.py`, ajouter après `WantedMovie` :

```python
class WantedSeries(BaseModel):
    tmdb_id: int
    title: str
    year: str | None = None
    poster_path: str | None = None
    added_at: datetime
    grabbed: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def poster_url(self) -> str | None:
        if not self.poster_path:
            return None
        return f"https://image.tmdb.org/t/p/w342{self.poster_path}"
```

Vérifier que `Field` est importé en tête de `torsearch/models.py` ; sinon ajouter `Field` à la
ligne `from pydantic import ...`.

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_models.py -q -k wanted_series`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add torsearch/models.py tests/test_models.py
git commit -m "feat: add WantedSeries model"
```

---

## Task 3 : Store `SeriesLibrary`

**Files:** Create `torsearch/library/series.py` ; Test `tests/test_series_library.py`

- [ ] **Step 1 : Test**

Créer `tests/test_series_library.py` :

```python
from datetime import datetime, timezone

from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedSeries

NOW = datetime(2026, 6, 21, tzinfo=timezone.utc)


def _series(tmdb_id=1, title="Show"):
    return WantedSeries(tmdb_id=tmdb_id, title=title, year="2024", added_at=NOW)


def test_add_and_list_persists(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    assert lib.add(_series()) is True
    assert [s.title for s in SeriesLibrary(tmp_path / "series.json").list()] == ["Show"]


def test_add_dedupes(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series())
    assert lib.add(_series(title="Show bis")) is False
    assert len(lib.list()) == 1


def test_remove(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series(1))
    lib.add(_series(2, "Other"))
    lib.remove(1)
    assert [s.tmdb_id for s in lib.list()] == [2]


def test_mark_grabbed_unions_keys(tmp_path):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(_series(1))
    lib.mark_grabbed(1, ["S01E01", "S01E02"])
    lib.mark_grabbed(1, ["S01E02", "S01E03"])
    assert lib.list()[0].grabbed == ["S01E01", "S01E02", "S01E03"]
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_series_library.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.library.series'`

- [ ] **Step 3 : Implémenter**

Créer `torsearch/library/series.py` :

```python
from __future__ import annotations

import json
import os
from pathlib import Path

from torsearch.models import WantedSeries


class SeriesLibrary:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[WantedSeries]:
        if not self._path.exists():
            return []
        return [WantedSeries.model_validate(item) for item in json.loads(self._path.read_text())]

    def _save(self, items: list[WantedSeries]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([s.model_dump(mode="json") for s in items], indent=2))
        os.replace(tmp, self._path)

    def list(self) -> list[WantedSeries]:
        return self._load()

    def add(self, series: WantedSeries) -> bool:
        items = self._load()
        if any(s.tmdb_id == series.tmdb_id for s in items):
            return False
        items.append(series)
        self._save(items)
        return True

    def remove(self, tmdb_id: int) -> None:
        self._save([s for s in self._load() if s.tmdb_id != tmdb_id])

    def mark_grabbed(self, tmdb_id: int, keys: list[str]) -> None:
        items = self._load()
        for i, s in enumerate(items):
            if s.tmdb_id == tmdb_id:
                merged = sorted(set(s.grabbed) | set(keys))
                items[i] = s.model_copy(update={"grabbed": merged})
        self._save(items)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_series_library.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/library/series.py tests/test_series_library.py
git commit -m "feat: add SeriesLibrary JSON store"
```

---

## Task 4 : `run_series_cycle`

**Files:** Modify `torsearch/monitor/runner.py` ; Test `tests/test_monitor_runner.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_monitor_runner.py` (réutilise `_r`, `FakeSearch`, `FakeTransmission`, `MNOW`) :

```python
from torsearch.library.series import SeriesLibrary
from torsearch.models import WantedSeries
from torsearch.monitor.runner import run_series_cycle


def _slib(tmp_path, grabbed=None):
    lib = SeriesLibrary(tmp_path / "series.json")
    lib.add(WantedSeries(tmdb_id=1, title="Show", year="2024", added_at=MNOW,
                         grabbed=grabbed or []))
    return lib


async def test_series_cycle_grabs_multiple_new_episodes(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    created = await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.1080p", seeders=50, infohash="A"),
        _r("Show.S01E02.1080p", seeders=40, infohash="B"),
    ]), tr, history)
    assert len(tr.added) == 2
    assert [r.kind for r in created] == ["grabbed", "grabbed"]
    assert lib.list()[0].grabbed == ["S01E01", "S01E02"]


async def test_series_cycle_dedupes_same_episode(tmp_path):
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    await run_series_cycle(cfg, lib, FakeSearch([
        _r("Show.S01E01.2160p", seeders=80, infohash="A"),
        _r("Show.S01E01.1080p", seeders=50, infohash="B"),
    ]), tr, MonitorHistory(tmp_path / "m.json"))
    assert len(tr.added) == 1


async def test_series_cycle_skips_already_grabbed(tmp_path):
    lib = _slib(tmp_path, grabbed=["S01E01"])
    cfg = Config(monitor=MonitorConfig(enabled=True))
    tr = FakeTransmission()
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                                 tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []


async def test_series_cycle_disabled_globally(tmp_path):
    cfg = Config(monitor=MonitorConfig(enabled=False))
    out = await run_series_cycle(cfg, _slib(tmp_path), FakeSearch([_r("Show.S01E01", infohash="A")]),
                                 FakeTransmission(), MonitorHistory(tmp_path / "m.json"))
    assert out == []


async def test_series_cycle_respects_quality_profile(tmp_path):
    from torsearch.config import LibraryConfig
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), library=LibraryConfig(qualities=["2160p"]))
    tr = FakeTransmission()
    out = await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", seeders=50, infohash="A")]),
                                 tr, MonitorHistory(tmp_path / "m.json"))
    assert out == []
    assert tr.added == []
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_monitor_runner.py -q -k series_cycle`
Expected: FAIL — `ImportError: cannot import name 'run_series_cycle'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/monitor/runner.py`, ajouter l'import en tête :

```python
from torsearch.library.episodes import parse_episodes
```

Ajouter la fonction après `run_movie_cycle` :

```python
async def run_series_cycle(config, series_library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]:
    if not config.monitor.enabled or series_library is None:
        return []
    profile = config.library
    created: list[MonitorRecord] = []
    for series in series_library.list():
        try:
            results = await search_service.search(series.title, Category.TV)
        except Exception as exc:
            logger.warning("Series search '%s' failed: %s", series.title, exc)
            continue
        kept = apply(results, ResultFilters(
            min_seeders=profile.min_seeders, qualities=profile.qualities,
            sort="seeders", direction="desc",
        ))
        have = set(series.grabbed)
        newly: list[str] = []
        for r in kept:
            keys = parse_episodes(r.title)
            if not keys - have:
                continue
            try:
                transmission.add(r.download_url)
            except Exception as exc:
                logger.warning("Series grab '%s' failed: %s", series.title, exc)
                continue
            have |= keys
            newly.extend(keys)
            now = datetime.now(timezone.utc)
            record = MonitorRecord(
                search=series.title, title=r.title, source=r.source,
                infohash=r.infohash, download_url=r.download_url, kind="grabbed", at=now,
            )
            history.add(record)
            created.append(record)
            if notifier is not None:
                try:
                    await notifier.notify(config.notifications, record)
                except Exception as exc:
                    logger.warning("Series notif '%s' failed: %s", series.title, exc)
        if newly:
            series_library.mark_grabbed(series.tmdb_id, sorted(set(newly)))
    return created
```

Modifier `MonitorRunner.__init__` :

```python
    def __init__(self, ctx, history, notifier=None, library=None, series_library=None):
        self._ctx = ctx
        self._history = history
        self._notifier = notifier or Notifier()
        self._library = library
        self._series_library = series_library
        self._task = None
```

Dans `MonitorRunner._loop`, après l'appel à `run_movie_cycle(...)`, ajouter :

```python
                await run_series_cycle(
                    self._ctx.config, self._series_library, self._ctx.search_service,
                    self._ctx.transmission, self._history, self._notifier,
                )
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_monitor_runner.py -q`
Expected: PASS (anciens + 5 nouveaux `series_cycle`)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/monitor/runner.py tests/test_monitor_runner.py
git commit -m "feat: auto-grab new series episodes in the monitor cycle"
```

---

## Task 5 : Câblage `series_library`

**Files:** Modify `torsearch/main.py`, `torsearch/web/routes.py` ; Test `tests/test_main.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_main.py` (après `assert app.state.library is not None`) :

```python
    assert app.state.series_library is not None
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_main.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'series_library'`

- [ ] **Step 3 : Câbler `create_app`**

Dans `torsearch/web/routes.py`, modifier la signature de `create_app` :

```python
def create_app(
    ctx: AppContext, history=None, monitor=None, auth: AuthSettings | None = None, library=None,
    series_library=None,
) -> FastAPI:
```

Après `app.state.library = library`, ajouter :

```python
    app.state.series_library = series_library
```

- [ ] **Step 4 : Câbler `build_app`**

Dans `torsearch/main.py`, ajouter l'import :

```python
from torsearch.library.series import SeriesLibrary
```

Ajouter la constante après `DEFAULT_LIBRARY_PATH` :

```python
DEFAULT_SERIES_PATH = os.environ.get("TORSEARCH_SERIES", "data/series.json")
```

Modifier `build_app` (signature + corps) :

```python
def build_app(
    settings_path: str = DEFAULT_SETTINGS_PATH,
    bootstrap_config_path: str = DEFAULT_CONFIG_PATH,
    monitor_path: str = DEFAULT_MONITOR_PATH,
    library_path: str = DEFAULT_LIBRARY_PATH,
    series_path: str = DEFAULT_SERIES_PATH,
) -> FastAPI:
    store = SettingsStore(settings_path, bootstrap_config_path=bootstrap_config_path)
    ctx = AppContext(store)
    history = MonitorHistory(monitor_path)
    library = MovieLibrary(library_path)
    series_library = SeriesLibrary(series_path)
    monitor = MonitorRunner(ctx, history, library=library, series_library=series_library)
    return create_app(
        ctx, history=history, monitor=monitor, auth=AuthSettings.from_env(),
        library=library, series_library=series_library,
    )
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_main.py -q`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add torsearch/main.py torsearch/web/routes.py tests/test_main.py
git commit -m "feat: wire SeriesLibrary into app and monitor"
```

---

## Task 6 : Web — section Séries + bouton Suivre

**Files:** Create `torsearch/web/series_routes.py`, `templates/partials/series_list.html` ; Modify `torsearch/web/library_routes.py`, `torsearch/web/routes.py`, `templates/library.html`, `templates/partials/media_results.html` ; Test `tests/test_series_web.py`

- [ ] **Step 1 : Test**

Créer `tests/test_series_web.py` :

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from torsearch.config import Config, MonitorConfig
from torsearch.library.movies import MovieLibrary
from torsearch.library.series import SeriesLibrary
from torsearch.models import MediaResult, WantedSeries
from torsearch.web.routes import create_app

NOW = datetime(2026, 6, 21, tzinfo=timezone.utc)


class FakeTmdb:
    enabled = True

    async def search(self, query):
        return [
            MediaResult(tmdb_id=1399, media_type="tv", title="Game of Thrones", year="2011",
                        poster_path="/g.jpg"),
        ]


class FakeCtx:
    def __init__(self):
        self.tmdb = FakeTmdb()
        self.config = Config(monitor=MonitorConfig(enabled=True))


def _client(tmp_path):
    movies = MovieLibrary(tmp_path / "lib.json")
    series = SeriesLibrary(tmp_path / "series.json")
    return TestClient(create_app(FakeCtx(), library=movies, series_library=series)), series


def test_series_add_persists(tmp_path):
    client, series = _client(tmp_path)
    resp = client.post("/series/add", data={"tmdb_id": "1399", "title": "GoT", "year": "2011", "poster_path": "/g.jpg"})
    assert resp.status_code == 200
    assert [s.tmdb_id for s in series.list()] == [1399]


def test_library_shows_series_section_with_episode_count(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1, title="My Show", year="2024", added_at=NOW,
                            grabbed=["S01E01", "S01E02"]))
    html = client.get("/library").text
    assert "My Show" in html
    assert "2 episodes" in html
    assert "Series" in html  # titre de section


def test_series_remove(tmp_path):
    client, series = _client(tmp_path)
    series.add(WantedSeries(tmdb_id=1, title="My Show", added_at=NOW))
    client.post("/series/1/remove")
    assert series.list() == []


def test_discover_series_card_has_follow_button(tmp_path):
    client, _ = _client(tmp_path)
    html = client.get("/discover/search", params={"q": "got"}).text
    assert 'hx-post="/series/add"' in html
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_series_web.py -q`
Expected: FAIL — `404` / `series_router` absent

- [ ] **Step 3 : Créer `series_routes.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from torsearch.models import WantedSeries
from torsearch.web.templating import templates

series_router = APIRouter()


@series_router.post("/series/add", response_class=HTMLResponse)
async def series_add(
    request: Request,
    tmdb_id: int = Form(...),
    title: str = Form(...),
    year: str = Form(""),
    poster_path: str = Form(""),
):
    series_library = request.app.state.series_library
    added = series_library.add(WantedSeries(
        tmdb_id=tmdb_id, title=title, year=year or None, poster_path=poster_path or None,
        added_at=datetime.now(timezone.utc),
    ))
    message = "Serie suivie." if added else "Serie deja suivie."
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": True, "message": message})


@series_router.post("/series/{tmdb_id}/remove", response_class=HTMLResponse)
async def series_remove(request: Request, tmdb_id: int):
    series_library = request.app.state.series_library
    series_library.remove(tmdb_id)
    return templates.TemplateResponse(request, "partials/series_list.html", {"series": series_library.list()})
```

- [ ] **Step 4 : `library_page` lit aussi les séries**

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
         "monitor_on": ctx.config.monitor.enabled},
    )
```

- [ ] **Step 5 : `library.html` à deux sections**

Remplacer le contenu de `torsearch/web/templates/library.html` par :

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-4 text-lg font-semibold">Bibliotheque</h1>
{% if not monitor_on %}
<div class="mb-5 rounded-lg border border-amber-600/40 bg-amber-600/10 px-4 py-3 text-sm">
  <i class="ti ti-alert-triangle text-amber-400"></i> La surveillance est desactivee : active-la dans <a href="/surveillance" class="underline text-amber-300 hover:text-amber-200">Surveillance</a> pour l'auto-grab.
</div>
{% endif %}
<section class="mb-8">
  <h2 class="mb-3 font-semibold text-slate-300">Films</h2>
  {% include "partials/library_list.html" %}
</section>
<section>
  <h2 class="mb-3 font-semibold text-slate-300">Series</h2>
  {% include "partials/series_list.html" %}
</section>
{% endblock %}
```

- [ ] **Step 6 : Créer `partials/series_list.html`**

```html
<div id="series-list">
{% if not series %}
  <p class="text-slate-400">Aucune serie suivie. Ajoute-en depuis <a href="/discover" class="underline hover:text-emerald-400">Decouvrir</a>.</p>
{% else %}
<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
  {% for s in series %}
  <div class="overflow-hidden rounded-lg border border-slate-800 bg-slate-800/40">
    <div class="aspect-[2/3] bg-slate-900">
      {% if s.poster_url %}
      <img src="{{ s.poster_url }}" alt="{{ s.title }}" class="h-full w-full object-cover" loading="lazy">
      {% else %}
      <div class="flex h-full items-center justify-center text-slate-600"><i class="ti ti-photo text-3xl"></i></div>
      {% endif %}
    </div>
    <div class="p-2.5">
      <div class="flex items-center gap-1.5">
        <span class="rounded px-1.5 py-0.5 text-[10px] bg-violet-500/15 text-violet-300">{{ s.grabbed | length }} episodes</span>
        {% if s.year %}<span class="text-[11px] text-slate-500">{{ s.year }}</span>{% endif %}
      </div>
      <div class="mt-1 truncate text-sm text-slate-100" title="{{ s.title }}">{{ s.title }}</div>
      <button hx-post="/series/{{ s.tmdb_id }}/remove" hx-target="#series-list" hx-swap="outerHTML"
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

- [ ] **Step 7 : Bouton « Suivre » sur les cartes série (Découvrir)**

Dans `torsearch/web/templates/partials/media_results.html`, remplacer le bloc
`{% if m.media_type == 'movie' %}…{% endif %}` (bouton Bibliotheque) par :

```html
      {% if m.media_type == 'movie' %}
      <button hx-post="/library/add" hx-target="#toast"
              hx-vals='{{ {"tmdb_id": m.tmdb_id, "title": m.title, "year": (m.year or ""), "poster_path": (m.poster_path or "")} | tojson }}'
              class="mt-1.5 flex w-full items-center justify-center gap-1 rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:text-emerald-400">
        <i class="ti ti-bookmark-plus"></i> Bibliotheque
      </button>
      {% elif m.media_type == 'tv' %}
      <button hx-post="/series/add" hx-target="#toast"
              hx-vals='{{ {"tmdb_id": m.tmdb_id, "title": m.title, "year": (m.year or ""), "poster_path": (m.poster_path or "")} | tojson }}'
              class="mt-1.5 flex w-full items-center justify-center gap-1 rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:text-emerald-400">
        <i class="ti ti-bookmark-plus"></i> Suivre
      </button>
      {% endif %}
```

- [ ] **Step 8 : Inclure `series_router`**

Dans `torsearch/web/routes.py`, après `from torsearch.web.library_routes import library_router` :

```python
from torsearch.web.series_routes import series_router
```

Après `app.include_router(library_router)` :

```python
    app.include_router(series_router)
```

- [ ] **Step 9 : Vérifier le succès**

Run: `uv run pytest tests/test_series_web.py tests/test_library_web.py -q`
Expected: PASS (séries + non-régression bibliothèque films)

- [ ] **Step 10 : Commit**

```bash
git add torsearch/web/series_routes.py torsearch/web/templates/partials/series_list.html torsearch/web/library_routes.py torsearch/web/routes.py torsearch/web/templates/library.html torsearch/web/templates/partials/media_results.html tests/test_series_web.py
git commit -m "feat: series section in library, follow button, series routes"
```

---

## Task 7 : Vérification finale

- [ ] **Step 1 : Toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante (204) + nouveaux tests (parser, models, series_library, monitor_runner, main, series_web), aucune régression.

- [ ] **Step 2 : Vérif visuelle (optionnel, manuel)**

Lancer l'app (clé TMDB + surveillance ON + un tracker), Découvrir une série → « Suivre » → `/library` section Séries → après un cycle monitor, le compteur d'épisodes monte.

---

## Self-review (notes)

- **Couverture spec :** parser `parse_episodes` (T1), `WantedSeries` (T2), `SeriesLibrary` (T3), `run_series_cycle`+runner (T4), câblage build_app/create_app (T5), section Séries + `/series/add`+`/series/{id}/remove` + bouton Suivre (T6), non-régression (T7). ✔
- **Cohérence des noms :** `parse_episodes`, `WantedSeries(tmdb_id,title,year,poster_path,added_at,grabbed)`, `SeriesLibrary.list/add/remove/mark_grabbed`, `run_series_cycle(config,series_library,search_service,transmission,history,notifier)`, `app.state.series_library`, routes `/series/add` `/series/{tmdb_id}/remove`, cible `#series-list`. ✔
- **Pas de placeholder :** code/markup/commandes exacts partout.
- **Note échappement :** bouton « Suivre » utilise `hx-vals='… | tojson'` en guillemets simples (leçon Phase A).
