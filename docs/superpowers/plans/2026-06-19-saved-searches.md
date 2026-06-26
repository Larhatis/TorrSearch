# F2 — Recherches sauvegardées + surveillance auto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enregistrer des recherches et les surveiller périodiquement en tâche de fond ; chaque nouveau résultat matchant est soit envoyé à Transmission (mode `auto`), soit signalé (mode `notify`).

**Architecture:** Les recherches + le réglage de surveillance vivent dans `Config` (persistées via `SettingsStore`, hot-reload). Un `MonitorHistory` (`data/monitor.json`) garde l'historique et sert l'anti-doublon. La logique `run_cycle` (pure, injectée) est jouée en boucle par un `MonitorRunner` asyncio démarré au lancement (lifespan FastAPI). Une page `/surveillance` pilote tout en HTMX.

**Tech Stack:** Python 3.12+ (3.14 local) · FastAPI (lifespan) · asyncio · Pydantic v2 (modèles frozen) · Jinja2 + HTMX · pytest (asyncio auto).

**Base :** branche `feat/saved-searches` (sur `feat/downloads-view`, qui contient F1+F3). Commandes via `.venv/bin/python -m pytest ...`. Code réutilisé : `torsearch/config.py` (modèles **frozen** `Config/IndexerConfig/TransmissionConfig/SearchConfig`, `AuthMode`, `load_config`, `ConfigDict`), `torsearch/models.py` (`Category`, `SearchResult`), `torsearch/settings/mutations.py` (`SettingsError`, `_index_of`, mutations indexers, `model_copy`), `torsearch/settings/store.py` (`SettingsStore`, écriture atomique), `torsearch/context.py` (`AppContext`), `torsearch/search/filters.py` (`ResultFilters`, `apply`), `torsearch/web/routes.py` (`create_app(ctx)` montant `router`+`settings_router`+`downloads_router`, `templates` de `torsearch.web.templating`), `torsearch/main.py` (`build_app`).

---

## File Structure

| Fichier | Action |
|---|---|
| `torsearch/config.py` | Modifier — `SavedSearch`, `MonitorConfig`, champs `Config`. |
| `torsearch/settings/mutations.py` | Modifier — mutations recherches + `set_monitor`. |
| `torsearch/monitor/__init__.py` | Créer (vide). |
| `torsearch/monitor/history.py` | Créer — `MonitorRecord`, `MonitorHistory`. |
| `torsearch/monitor/runner.py` | Créer — `grab_key`, `select_new`, `run_cycle`, `MonitorRunner`. |
| `torsearch/web/routes.py` | Modifier — `create_app(ctx, history, monitor)` + lifespan + mount surveillance. |
| `torsearch/main.py` | Modifier — historique + runner. |
| `torsearch/web/surveillance_routes.py` | Créer — `surveillance_router`. |
| `torsearch/web/templates/surveillance.html` + `partials/surveillance_body.html` | Créer. |
| `torsearch/web/templates/base.html` | Modifier — lien nav. |
| `tests/test_config.py`, `tests/test_settings_mutations.py`, `tests/test_main.py` | Modifier. |
| `tests/test_monitor_history.py`, `tests/test_monitor_runner.py`, `tests/test_surveillance_web.py` | Créer. |

---

## Task 1: Modèles SavedSearch + MonitorConfig

**Files:**
- Modify: `torsearch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_config.py`)**

```python
def test_saved_search_defaults():
    from torsearch.config import SavedSearch
    ss = SavedSearch(name="x", query="q")
    assert ss.category.value == "all"
    assert ss.mode == "auto"
    assert ss.enabled is True
    assert ss.min_seeders == 0


def test_config_round_trips_saved_searches_and_monitor():
    from torsearch.config import Config, MonitorConfig, SavedSearch
    cfg = Config(
        saved_searches=[SavedSearch(name="s1", query="dune", mode="notify")],
        monitor=MonitorConfig(enabled=True, interval_minutes=15),
    )
    again = Config.model_validate_json(cfg.model_dump_json())
    assert again.saved_searches[0].name == "s1"
    assert again.saved_searches[0].mode == "notify"
    assert again.monitor.enabled is True
    assert again.monitor.interval_minutes == 15


def test_monitor_defaults_off():
    from torsearch.config import Config
    cfg = Config()
    assert cfg.monitor.enabled is False
    assert cfg.monitor.interval_minutes == 30
    assert cfg.saved_searches == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'SavedSearch'`.

- [ ] **Step 3: Add the models to `torsearch/config.py`**

At the top of `torsearch/config.py`, add to the imports:
```python
from torsearch.models import Category
```
Add these two model classes (after `SearchConfig`, before `Config`):
```python
class SavedSearch(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    query: str
    category: Category = Category.ALL
    min_seeders: int = 0
    min_size: int | None = None
    max_size: int | None = None
    qualities: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    mode: str = "auto"
    enabled: bool = True


class MonitorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    enabled: bool = False
    interval_minutes: int = 30
```
Add these two fields to the `Config` model:
```python
    saved_searches: list[SavedSearch] = Field(default_factory=list)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (the 3 new tests + all pre-existing config tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add SavedSearch and MonitorConfig models"
```

---

## Task 2: Mutations recherches sauvegardées + monitor

**Files:**
- Modify: `torsearch/settings/mutations.py`
- Test: `tests/test_settings_mutations.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_settings_mutations.py`)**

```python
def test_add_saved_search_and_reject_duplicate():
    from torsearch.config import SavedSearch
    from torsearch.settings.mutations import add_saved_search
    cfg = Config()
    cfg2 = add_saved_search(cfg, SavedSearch(name="s", query="q"))
    assert [s.name for s in cfg2.saved_searches] == ["s"]
    assert cfg.saved_searches == []  # original untouched
    with pytest.raises(SettingsError):
        add_saved_search(cfg2, SavedSearch(name="s", query="q2"))


def test_remove_and_toggle_saved_search():
    from torsearch.config import SavedSearch
    from torsearch.settings.mutations import remove_saved_search, set_saved_search_enabled
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q", enabled=True)])
    assert set_saved_search_enabled(cfg, "s", False).saved_searches[0].enabled is False
    assert remove_saved_search(cfg, "s").saved_searches == []
    with pytest.raises(SettingsError):
        remove_saved_search(cfg, "nope")


def test_set_monitor():
    from torsearch.config import MonitorConfig
    from torsearch.settings.mutations import set_monitor
    out = set_monitor(Config(), MonitorConfig(enabled=True, interval_minutes=10))
    assert out.monitor.enabled is True
    assert out.monitor.interval_minutes == 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -v`
Expected: FAIL — `ImportError: cannot import name 'add_saved_search'`.

- [ ] **Step 3: Append to `torsearch/settings/mutations.py`**

Extend the import line to also bring in the new models:
```python
from torsearch.config import Config, IndexerConfig, MonitorConfig, SavedSearch, SearchConfig, TransmissionConfig
```
Append these functions:
```python
def _saved_index(config: Config, name: str) -> int:
    for i, ss in enumerate(config.saved_searches):
        if ss.name == name:
            return i
    return -1


def add_saved_search(config: Config, saved_search: SavedSearch) -> Config:
    if _saved_index(config, saved_search.name) != -1:
        raise SettingsError(f"Une recherche nommée « {saved_search.name} » existe déjà.")
    return config.model_copy(update={"saved_searches": [*config.saved_searches, saved_search]})


def remove_saved_search(config: Config, name: str) -> Config:
    if _saved_index(config, name) == -1:
        raise SettingsError(f"Recherche introuvable : « {name} ».")
    return config.model_copy(
        update={"saved_searches": [s for s in config.saved_searches if s.name != name]}
    )


def set_saved_search_enabled(config: Config, name: str, enabled: bool) -> Config:
    idx = _saved_index(config, name)
    if idx == -1:
        raise SettingsError(f"Recherche introuvable : « {name} ».")
    new = list(config.saved_searches)
    new[idx] = new[idx].model_copy(update={"enabled": enabled})
    return config.model_copy(update={"saved_searches": new})


def set_monitor(config: Config, monitor: MonitorConfig) -> Config:
    return config.model_copy(update={"monitor": monitor})
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_settings_mutations.py -v`
Expected: PASS (3 new + all pre-existing).

- [ ] **Step 5: Commit**

```bash
git add torsearch/settings/mutations.py tests/test_settings_mutations.py
git commit -m "feat: add saved-search and monitor config mutations"
```

---

## Task 3: Historique de surveillance

**Files:**
- Create: `torsearch/monitor/__init__.py` (empty), `torsearch/monitor/history.py`
- Test: `tests/test_monitor_history.py`

- [ ] **Step 1: Write the failing test**

`tests/test_monitor_history.py`:
```python
from datetime import datetime, timezone

from torsearch.monitor.history import MonitorHistory, MonitorRecord


def _rec(search="s", title="T", infohash="H", url="magnet:?xt=urn:btih:H", kind="grabbed"):
    return MonitorRecord(search=search, title=title, source="src", infohash=infohash,
                         download_url=url, kind=kind, at=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_records_empty_when_no_file(tmp_path):
    assert MonitorHistory(tmp_path / "none.json").records() == []


def test_add_and_records_most_recent_first(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(title="first", infohash="H1", url="u1"))
    h.add(_rec(title="second", infohash="H2", url="u2"))
    assert [r.title for r in h.records()] == ["second", "first"]


def test_seen_keys_per_search(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(search="a", infohash="HA", url="u1"))
    h.add(_rec(search="b", infohash="HB", url="u2"))
    assert h.seen_keys("a") == {"HA"}
    assert h.seen_keys("b") == {"HB"}
    assert h.seen_keys("none") == set()


def test_seen_keys_falls_back_to_url(tmp_path):
    h = MonitorHistory(tmp_path / "monitor.json")
    h.add(_rec(search="a", infohash=None, url="http://x/t.torrent"))
    assert h.seen_keys("a") == {"http://x/t.torrent"}


def test_persistence_round_trip_and_atomic(tmp_path):
    path = tmp_path / "monitor.json"
    MonitorHistory(path).add(_rec())
    assert MonitorHistory(path).records()[0].title == "T"
    assert not path.with_name(path.name + ".tmp").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_monitor_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.monitor'`.

- [ ] **Step 3: Write the implementation**

Create empty `torsearch/monitor/__init__.py`.

`torsearch/monitor/history.py`:
```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class MonitorRecord(BaseModel):
    search: str
    title: str
    source: str
    infohash: str | None = None
    download_url: str
    kind: str  # "grabbed" | "found"
    at: datetime


class MonitorHistory:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _load(self) -> list[MonitorRecord]:
        if not self._path.exists():
            return []
        return [MonitorRecord.model_validate(item) for item in json.loads(self._path.read_text())]

    def records(self) -> list[MonitorRecord]:
        return list(reversed(self._load()))

    def seen_keys(self, search_name: str) -> set[str]:
        return {
            r.infohash or r.download_url
            for r in self._load()
            if r.search == search_name
        }

    def add(self, record: MonitorRecord) -> None:
        existing = self._load()
        existing.append(record)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps([r.model_dump(mode="json") for r in existing], indent=2))
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_monitor_history.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/monitor/__init__.py torsearch/monitor/history.py tests/test_monitor_history.py
git commit -m "feat: add monitor history with dedup keys"
```

---

## Task 4: Logique de surveillance (run_cycle + runner)

**Files:**
- Create: `torsearch/monitor/runner.py`
- Test: `tests/test_monitor_runner.py`

- [ ] **Step 1: Write the failing test**

`tests/test_monitor_runner.py`:
```python
from torsearch.config import Config, MonitorConfig, SavedSearch
from torsearch.models import Category, SearchResult
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import MonitorRunner, run_cycle, select_new
from torsearch.search.filters import ResultFilters


def _r(title, seeders=10, infohash=None, url=None):
    return SearchResult(title=title, size=1000, seeders=seeders, leechers=0, source="trk",
                        category=Category.MOVIES, download_url=url or ("magnet:?xt=urn:btih:" + title),
                        infohash=infohash)


class FakeSearch:
    def __init__(self, results, error=False):
        self._results = results
        self._error = error

    async def search(self, query, category):
        if self._error:
            raise RuntimeError("boom")
        return list(self._results)


class FakeTransmission:
    def __init__(self):
        self.added = []

    def add(self, url):
        self.added.append(url)
        return 1


def test_select_new_picks_best_unseen():
    res = [_r("low", seeders=5, infohash="A"), _r("high", seeders=50, infohash="B")]
    assert select_new(res, ResultFilters(), set()).title == "high"
    assert select_new(res, ResultFilters(), {"B"}).title == "low"
    assert select_new(res, ResultFilters(), {"A", "B"}) is None


async def test_run_cycle_auto_grabs_and_records(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    tr = FakeTransmission()
    created = await run_cycle(cfg, FakeSearch([_r("Best", seeders=99, infohash="X")]), tr, history)
    assert tr.added == ["magnet:?xt=urn:btih:Best"]
    assert [r.kind for r in created] == ["grabbed"]
    assert history.seen_keys("s") == {"X"}


async def test_run_cycle_notify_records_without_grab(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="notify")])
    tr = FakeTransmission()
    created = await run_cycle(cfg, FakeSearch([_r("Found", infohash="Y")]), tr, history)
    assert tr.added == []
    assert [r.kind for r in created] == ["found"]


async def test_run_cycle_skips_already_seen(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="s", query="q", mode="auto")])
    search = FakeSearch([_r("Best", infohash="X")])
    await run_cycle(cfg, search, FakeTransmission(), history)
    assert await run_cycle(cfg, search, FakeTransmission(), history) == []


async def test_run_cycle_disabled_globally(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=False), saved_searches=[SavedSearch(name="s", query="q")])
    assert await run_cycle(cfg, FakeSearch([_r("X", infohash="Z")]), FakeTransmission(), history) == []


async def test_run_cycle_disabled_search_ignored(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True),
                 saved_searches=[SavedSearch(name="off", query="q", enabled=False)])
    assert await run_cycle(cfg, FakeSearch([_r("X", infohash="Z")]), FakeTransmission(), history) == []


async def test_run_cycle_resilient_to_search_error(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")
    cfg = Config(monitor=MonitorConfig(enabled=True), saved_searches=[SavedSearch(name="s", query="q")])
    assert await run_cycle(cfg, FakeSearch([], error=True), FakeTransmission(), history) == []


async def test_runner_start_and_stop(tmp_path):
    history = MonitorHistory(tmp_path / "m.json")

    class Ctx:
        config = Config(monitor=MonitorConfig(enabled=False))
        search_service = FakeSearch([])
        transmission = FakeTransmission()

    runner = MonitorRunner(Ctx(), history)
    await runner.start()
    assert runner._task is not None
    await runner.stop()
    assert runner._task is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_monitor_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.monitor.runner'`.

- [ ] **Step 3: Write the implementation**

`torsearch/monitor/runner.py`:
```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from torsearch.models import SearchResult
from torsearch.monitor.history import MonitorRecord
from torsearch.search.filters import ResultFilters, apply

logger = logging.getLogger(__name__)


def grab_key(result: SearchResult) -> str:
    return result.infohash or result.download_url


def select_new(results, filters, seen):
    for result in apply(results, filters):
        if grab_key(result) not in seen:
            return result
    return None


async def run_cycle(config, search_service, transmission, history) -> list[MonitorRecord]:
    if not config.monitor.enabled:
        return []
    created: list[MonitorRecord] = []
    for saved in config.saved_searches:
        if not saved.enabled:
            continue
        try:
            results = await search_service.search(saved.query, saved.category)
        except Exception as exc:
            logger.warning("Monitor search '%s' failed: %s", saved.name, exc)
            continue
        filters = ResultFilters(
            min_seeders=saved.min_seeders, min_size=saved.min_size, max_size=saved.max_size,
            qualities=saved.qualities, exclude=saved.exclude, sort="seeders", direction="desc",
        )
        pick = select_new(results, filters, history.seen_keys(saved.name))
        if pick is None:
            continue
        if saved.mode == "auto":
            try:
                transmission.add(pick.download_url)
            except Exception as exc:
                logger.warning("Monitor grab for '%s' failed: %s", saved.name, exc)
                continue
            kind = "grabbed"
        else:
            kind = "found"
        record = MonitorRecord(
            search=saved.name, title=pick.title, source=pick.source,
            infohash=pick.infohash, download_url=pick.download_url,
            kind=kind, at=datetime.now(timezone.utc),
        )
        history.add(record)
        created.append(record)
    return created


class MonitorRunner:
    def __init__(self, ctx, history):
        self._ctx = ctx
        self._history = history
        self._task = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await run_cycle(
                    self._ctx.config, self._ctx.search_service, self._ctx.transmission, self._history
                )
            except Exception:
                logger.exception("Monitor cycle failed")
            interval = max(self._ctx.config.monitor.interval_minutes, 1) * 60
            await asyncio.sleep(interval)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_monitor_runner.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/monitor/runner.py tests/test_monitor_runner.py
git commit -m "feat: add monitor cycle logic and background runner"
```

---

## Task 5: Câblage (lifespan + history + runner)

**Files:**
- Modify: `torsearch/web/routes.py`, `torsearch/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Update the main wiring test (failing first)**

Replace the body of `tests/test_main.py`'s test with this (keep the imports/`from torsearch import main`):
```python
def test_build_app_wires_context_history_and_bootstraps(tmp_path, monkeypatch):
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
    app = main.build_app(
        settings_path=str(settings),
        bootstrap_config_path=str(config),
        monitor_path=str(tmp_path / "data" / "monitor.json"),
    )
    assert [ix.name for ix in app.state.ctx.search_service.indexers] == ["tracker1"]
    assert settings.exists()
    assert app.state.history is not None
    assert app.state.history.records() == []
```

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `build_app()` has no `monitor_path` and does not set `app.state.history`.

- [ ] **Step 2: Update `create_app` in `torsearch/web/routes.py`**

Add at the top of the imports:
```python
from contextlib import asynccontextmanager
```
Replace the `create_app` function with:
```python
def create_app(ctx: AppContext, history=None, monitor=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if monitor is not None:
            await monitor.start()
        try:
            yield
        finally:
            if monitor is not None:
                await monitor.stop()

    app = FastAPI(title="TorSearch", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.history = history
    app.include_router(router)
    app.include_router(settings_router)
    app.include_router(downloads_router)
    return app
```
(Keep the existing route handlers and the `router`/`settings_router`/`downloads_router` imports unchanged. `surveillance_router` is added in Task 6.)

- [ ] **Step 3: Update `torsearch/main.py`**

Replace the entire contents of `torsearch/main.py` with:
```python
from __future__ import annotations

import os

from fastapi import FastAPI

from torsearch.context import AppContext
from torsearch.monitor.history import MonitorHistory
from torsearch.monitor.runner import MonitorRunner
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app

DEFAULT_SETTINGS_PATH = os.environ.get("TORSEARCH_SETTINGS", "data/settings.json")
DEFAULT_CONFIG_PATH = os.environ.get("TORSEARCH_CONFIG", "config.yaml")
DEFAULT_MONITOR_PATH = os.environ.get("TORSEARCH_MONITOR", "data/monitor.json")


def build_app(
    settings_path: str = DEFAULT_SETTINGS_PATH,
    bootstrap_config_path: str = DEFAULT_CONFIG_PATH,
    monitor_path: str = DEFAULT_MONITOR_PATH,
) -> FastAPI:
    store = SettingsStore(settings_path, bootstrap_config_path=bootstrap_config_path)
    ctx = AppContext(store)
    history = MonitorHistory(monitor_path)
    monitor = MonitorRunner(ctx, history)
    return create_app(ctx, history=history, monitor=monitor)


def get_app() -> FastAPI:
    return build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — `test_main` green, and all other tests still green (existing `create_app(ctx)` calls keep working since `history`/`monitor` default to `None`, and the lifespan does nothing without a monitor; plain `TestClient(app)` does not run the lifespan anyway).

- [ ] **Step 5: Commit**

```bash
git add torsearch/web/routes.py torsearch/main.py tests/test_main.py
git commit -m "feat: wire monitor history and background runner via lifespan"
```

---

## Task 6: Page /surveillance

**Files:**
- Create: `torsearch/web/surveillance_routes.py`, `torsearch/web/templates/surveillance.html`, `torsearch/web/templates/partials/surveillance_body.html`
- Modify: `torsearch/web/routes.py` (mount router), `torsearch/web/templates/base.html` (nav)
- Test: `tests/test_surveillance_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_surveillance_web.py`:
```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from torsearch.config import Config, SavedSearch
from torsearch.context import AppContext
from torsearch.monitor.history import MonitorHistory, MonitorRecord
from torsearch.settings.store import SettingsStore
from torsearch.web.routes import create_app


def _client(tmp_path, config=None, history=None):
    store = SettingsStore(tmp_path / "settings.json")
    if config is not None:
        store.save(config)
    ctx = AppContext(store)
    history = history if history is not None else MonitorHistory(tmp_path / "monitor.json")
    return TestClient(create_app(ctx, history=history)), ctx, history


def test_surveillance_page_renders(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/surveillance")
    assert resp.status_code == 200
    assert "Surveillance" in resp.text
    assert 'name="interval_minutes"' in resp.text


def test_add_saved_search(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/searches", data={"name": "MaSerie", "query": "ma serie", "cat": "tv", "mode": "notify"})
    assert resp.status_code == 200
    assert "MaSerie" in resp.text
    assert [s.name for s in ctx.config.saved_searches] == ["MaSerie"]
    assert ctx.config.saved_searches[0].mode == "notify"


def test_add_duplicate_shows_error(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q")])
    client, ctx, _ = _client(tmp_path, cfg)
    resp = client.post("/surveillance/searches", data={"name": "s", "query": "q2"})
    assert "existe" in resp.text
    assert len(ctx.config.saved_searches) == 1


def test_toggle_and_delete_saved_search(tmp_path):
    cfg = Config(saved_searches=[SavedSearch(name="s", query="q", enabled=True)])
    client, ctx, _ = _client(tmp_path, cfg)
    client.post("/surveillance/searches/s/toggle")
    assert ctx.config.saved_searches[0].enabled is False
    client.post("/surveillance/searches/s/delete")
    assert ctx.config.saved_searches == []


def test_update_monitor_settings(tmp_path):
    client, ctx, _ = _client(tmp_path)
    resp = client.post("/surveillance/monitor", data={"enabled": "on", "interval_minutes": "15"})
    assert resp.status_code == 200
    assert ctx.config.monitor.enabled is True
    assert ctx.config.monitor.interval_minutes == 15


def test_history_found_item_has_send_button(tmp_path):
    history = MonitorHistory(tmp_path / "monitor.json")
    history.add(MonitorRecord(search="s", title="Found.It", source="trk", infohash="H",
                              download_url="magnet:?xt=urn:btih:H", kind="found",
                              at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    client, _, _ = _client(tmp_path, history=history)
    resp = client.get("/surveillance")
    assert "Found.It" in resp.text
    assert "Envoyer" in resp.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_surveillance_web.py -v`
Expected: FAIL — `404` for `/surveillance` (router not mounted) / `ModuleNotFoundError`.

- [ ] **Step 3: Create the templates**

`torsearch/web/templates/surveillance.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-lg font-semibold mb-6">Surveillance</h1>
{% include "partials/surveillance_body.html" %}
{% endblock %}
```

`torsearch/web/templates/partials/surveillance_body.html`:
```html
<div id="surveillance-body">
  {% if error %}<div class="mb-3 rounded bg-red-600 px-3 py-2 text-sm">{{ error }}</div>{% endif %}
  {% if notice %}<div class="mb-3 rounded bg-emerald-600 px-3 py-2 text-sm">{{ notice }}</div>{% endif %}

  <section class="mb-8">
    <h2 class="font-semibold mb-2">Surveillance globale</h2>
    <form hx-post="/surveillance/monitor" hx-target="#surveillance-body" hx-swap="outerHTML" class="flex items-end gap-3">
      <label class="text-xs text-slate-400 flex items-center gap-1">
        <input type="checkbox" name="enabled" {% if monitor.enabled %}checked{% endif %}> activee</label>
      <label class="text-xs text-slate-400">Intervalle (min)<br>
        <input name="interval_minutes" value="{{ monitor.interval_minutes }}" class="w-24 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
    </form>
  </section>

  <section class="mb-8">
    <h2 class="font-semibold mb-2">Nouvelle recherche surveillee</h2>
    <form hx-post="/surveillance/searches" hx-target="#surveillance-body" hx-swap="outerHTML" class="flex flex-wrap items-end gap-2">
      <input name="name" placeholder="Nom" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
      <input name="query" placeholder="Recherche (ex: ma serie s02)" class="rounded bg-slate-800 border border-slate-700 px-2 py-1 w-64">
      <select name="cat" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
        {% for c in categories %}<option value="{{ c.value }}">{{ c.value | capitalize }}</option>{% endfor %}
      </select>
      <select name="mode" class="rounded bg-slate-800 border border-slate-700 px-2 py-1">
        <option value="auto">auto (envoi)</option><option value="notify">notify (signaler)</option>
      </select>
      <label class="text-xs text-slate-400">Seeders min<br>
        <input type="number" name="min_seeders" value="0" min="0" class="w-20 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille min (Go)<br>
        <input type="number" name="min_size_gb" step="0.1" min="0" class="w-20 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille max (Go)<br>
        <input type="number" name="max_size_gb" step="0.1" min="0" class="w-20 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <fieldset class="text-xs text-slate-400"><legend>Qualite</legend>
        <div class="flex gap-2">
          {% for qv in ["2160p", "1080p", "720p", "480p", "other"] %}
          <label class="flex items-center gap-1"><input type="checkbox" name="quality" value="{{ qv }}"> {{ qv }}</label>
          {% endfor %}
        </div>
      </fieldset>
      <label class="text-xs text-slate-400">Exclure<br>
        <input name="exclude" placeholder="cam, ts" class="w-40 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-sm">Ajouter</button>
    </form>
  </section>

  <section class="mb-8">
    <h2 class="font-semibold mb-2">Recherches surveillees</h2>
    {% for s in searches %}
    <div class="flex items-center gap-3 border-b border-slate-800 py-2 text-sm">
      <span class="font-medium">{{ s.name }}</span>
      <span class="text-slate-400">{{ s.query }}</span>
      <span class="rounded bg-slate-700 px-2 py-0.5 text-xs">{{ s.mode }}</span>
      <span class="ml-auto"></span>
      <button hx-post="/surveillance/searches/{{ s.name }}/toggle" hx-target="#surveillance-body" hx-swap="outerHTML"
              class="rounded {% if s.enabled %}bg-amber-600{% else %}bg-slate-600{% endif %} px-2 py-1 text-xs">
        {{ "Desactiver" if s.enabled else "Activer" }}</button>
      <button hx-post="/surveillance/searches/{{ s.name }}/delete" hx-target="#surveillance-body" hx-swap="outerHTML"
              class="rounded bg-red-700 px-2 py-1 text-xs">Supprimer</button>
    </div>
    {% else %}
    <p class="text-slate-400 text-sm">Aucune recherche surveillee.</p>
    {% endfor %}
  </section>

  <section>
    <h2 class="font-semibold mb-2">Historique</h2>
    {% for r in records %}
    <div class="flex items-center gap-3 border-b border-slate-800 py-2 text-sm">
      <span class="rounded px-2 py-0.5 text-xs {% if r.kind == 'grabbed' %}bg-emerald-700{% else %}bg-sky-700{% endif %}">{{ 'grabbe' if r.kind == 'grabbed' else 'trouve' }}</span>
      <span class="text-slate-400">{{ r.search }}</span>
      <span>{{ r.title }}</span>
      <span class="ml-auto text-slate-500 text-xs">{{ r.at.strftime('%Y-%m-%d %H:%M') }}</span>
      {% if r.kind == 'found' %}
      <form hx-post="/download" hx-target="#toast" class="inline">
        <input type="hidden" name="download_url" value="{{ r.download_url }}">
        <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-xs">Envoyer</button>
      </form>
      {% endif %}
    </div>
    {% else %}
    <p class="text-slate-400 text-sm">Aucune detection pour le moment.</p>
    {% endfor %}
  </section>
</div>
```

- [ ] **Step 4: Create the router**

`torsearch/web/surveillance_routes.py`:
```python
from __future__ import annotations

import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from torsearch.config import Category, MonitorConfig, SavedSearch
from torsearch.context import AppContext
from torsearch.settings.mutations import (
    SettingsError,
    add_saved_search,
    remove_saved_search,
    set_monitor,
    set_saved_search_enabled,
)
from torsearch.web.templating import templates

surveillance_router = APIRouter()

_GB = 1024 ** 3


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_size_bytes(value: str) -> int | None:
    try:
        gb = float(value)
    except (TypeError, ValueError):
        return None
    return int(gb * _GB) if gb > 0 else None


def _context(request: Request, error=None, notice=None):
    ctx: AppContext = request.app.state.ctx
    history = request.app.state.history
    records = history.records() if history is not None else []
    return {
        "config": ctx.config, "searches": ctx.config.saved_searches,
        "monitor": ctx.config.monitor, "records": records,
        "categories": list(Category), "error": error, "notice": notice,
    }


def _page(request, **kw):
    return templates.TemplateResponse(request, "surveillance.html", _context(request, **kw))


def _body(request, **kw):
    return templates.TemplateResponse(request, "partials/surveillance_body.html", _context(request, **kw))


@surveillance_router.get("/surveillance", response_class=HTMLResponse)
async def page(request: Request):
    return _page(request)


@surveillance_router.post("/surveillance/monitor", response_class=HTMLResponse)
async def update_monitor(request: Request, enabled: str | None = Form(None), interval_minutes: str = Form("30")):
    ctx: AppContext = request.app.state.ctx
    try:
        monitor = MonitorConfig(enabled=enabled is not None, interval_minutes=interval_minutes)
        ctx.update_settings(set_monitor(ctx.config, monitor))
        return _body(request, notice="Surveillance mise a jour.")
    except (ValidationError, SettingsError) as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches", response_class=HTMLResponse)
async def add_search(
    request: Request,
    name: str = Form(...),
    query: str = Form(...),
    cat: str = Form("all"),
    mode: str = Form("auto"),
    min_seeders: str = Form("0"),
    min_size_gb: str = Form(""),
    max_size_gb: str = Form(""),
    quality: list[str] = Form(default=[]),
    exclude: str = Form(""),
):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    try:
        saved = SavedSearch(
            name=name, query=query, category=category, mode=mode,
            min_seeders=max(_to_int(min_seeders), 0),
            min_size=_to_size_bytes(min_size_gb),
            max_size=_to_size_bytes(max_size_gb),
            qualities=[q for q in quality if q],
            exclude=[w for w in re.split(r"[\s,]+", exclude) if w],
        )
        ctx.update_settings(add_saved_search(ctx.config, saved))
        return _body(request, notice=f"Recherche « {name} » enregistree.")
    except (ValidationError, SettingsError) as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/toggle", response_class=HTMLResponse)
async def toggle_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    current = next((s for s in ctx.config.saved_searches if s.name == name), None)
    try:
        ctx.update_settings(
            set_saved_search_enabled(ctx.config, name, not current.enabled if current else True)
        )
        return _body(request)
    except SettingsError as exc:
        return _body(request, error=f"Erreur : {exc}")


@surveillance_router.post("/surveillance/searches/{name}/delete", response_class=HTMLResponse)
async def delete_search(request: Request, name: str):
    ctx: AppContext = request.app.state.ctx
    try:
        ctx.update_settings(remove_saved_search(ctx.config, name))
        return _body(request, notice=f"Recherche « {name} » supprimee.")
    except SettingsError as exc:
        return _body(request, error=f"Erreur : {exc}")
```

- [ ] **Step 5: Mount the router + add nav link**

In `torsearch/web/routes.py`, add an import next to the other `torsearch.web.*` imports:
```python
from torsearch.web.surveillance_routes import surveillance_router
```
and inside `create_app`, after `app.include_router(downloads_router)`, add:
```python
    app.include_router(surveillance_router)
```

In `torsearch/web/templates/base.html`, add a nav link after the « Telechargements » link:
```html
      <a href="/surveillance" class="hover:text-emerald-400">Surveillance</a>
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — the 6 new surveillance tests green, plus everything pre-existing.

- [ ] **Step 7: Commit**

```bash
git add torsearch/web/surveillance_routes.py torsearch/web/templates/surveillance.html torsearch/web/templates/partials/surveillance_body.html torsearch/web/routes.py torsearch/web/templates/base.html tests/test_surveillance_web.py
git commit -m "feat: add surveillance page for saved searches and monitor control"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. Lancer `uvicorn torsearch.main:get_app --factory --reload`, aller sur `/surveillance`, créer
   une recherche en mode `notify`, activer la **surveillance globale** avec un petit intervalle.
2. Attendre un cycle → un item « trouve » apparaît dans l'historique (sans envoi) ; cliquer
   **Envoyer** l'ajoute à Transmission.
3. Créer une recherche en mode `auto` → au cycle suivant, le meilleur nouveau résultat est envoyé
   automatiquement (item « grabbe »), et n'est pas repris au cycle d'après (anti-doublon).
4. Désactiver la surveillance globale → plus aucune action automatique.
