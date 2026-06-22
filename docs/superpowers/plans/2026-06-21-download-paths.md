# Routage des téléchargements par catégorie — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Placer chaque torrent dans le dossier de destination correspondant à sa catégorie (films/séries/…), via une table `catégorie → dossier` configurable.

**Architecture:** `PathsConfig.by_category` (map scalable) + `path_for`/`for_category` ; `TransmissionClient.add(url, download_dir)` ; les cycles auto-grab et la route `/download` résolvent le dossier par catégorie ; section Réglages générique.

**Tech Stack:** FastAPI, transmission-rpc, Jinja2/HTMX, pytest.

**Spec :** `docs/superpowers/specs/2026-06-21-download-paths-design.md`

---

## Structure des fichiers

- **Modifier** `torsearch/config.py` — `PathsConfig` + champ `paths`.
- **Modifier** `torsearch/transmission/client.py` — `add(url, download_dir=None)`.
- **Modifier** `torsearch/monitor/runner.py` — cycles passent `download_dir`.
- **Modifier** `torsearch/web/routes.py` — `/download` résout la catégorie ; `templates/partials/results.html`.
- **Modifier** `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `templates/settings.html`.
- **Tests** : `test_config.py`, `test_transmission.py`, `test_monitor_runner.py`, `test_web.py`, `test_settings_web.py`.

---

## Task 1 : `PathsConfig`

**Files:** Modify `torsearch/config.py` ; Test `tests/test_config.py`

- [ ] **Step 1 : Tests**

Ajouter à `tests/test_config.py` :

```python
def test_paths_for_category(tmp_path):
    from torsearch.config import load_config
    from torsearch.models import Category

    p = tmp_path / "c.yaml"
    p.write_text("paths:\n  by_category:\n    movies: /data/films\n    tv: /data/series\n")
    cfg = load_config(p)
    assert cfg.paths.for_category(Category.MOVIES) == "/data/films"
    assert cfg.paths.for_category(Category.TV) == "/data/series"
    assert cfg.paths.for_category(Category.ANIME) is None


def test_paths_default_empty(tmp_path):
    from torsearch.config import load_config
    from torsearch.models import Category

    p = tmp_path / "e.yaml"
    p.write_text("{}\n")
    assert load_config(p).paths.for_category(Category.MOVIES) is None
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_config.py -q -k paths`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'paths'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/config.py`, ajouter avant `class Config` :

```python
class PathsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    by_category: dict[str, str] = Field(default_factory=dict)

    def for_category(self, category: Category) -> str | None:
        return self.by_category.get(category.value) or None
```

Et dans `class Config`, après `jellyfin` :

```python
    paths: PathsConfig = Field(default_factory=PathsConfig)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_config.py -q -k paths`
Expected: PASS (2 tests)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/config.py tests/test_config.py
git commit -m "feat: add PathsConfig category-to-folder map"
```

---

## Task 2 : `TransmissionClient.add(download_dir)`

**Files:** Modify `torsearch/transmission/client.py` ; Test `tests/test_transmission.py`

- [ ] **Step 1 : Mettre à jour le fake + tests**

Dans `tests/test_transmission.py`, remplacer la méthode `add_torrent` de la classe `FakeRpc` par :

```python
    def add_torrent(self, url, download_dir=None):
        self.added.append(url)
        self.last_download_dir = download_dir
        return SimpleNamespace(id=42)
```

Ajouter ce test (après `test_add_returns_torrent_id_and_passes_url`) :

```python
def test_add_passes_download_dir():
    captured = {}

    def factory(**kwargs):
        captured["client"] = FakeRpc(**kwargs)
        return captured["client"]

    tc = TransmissionClient(TransmissionConfig(), client_factory=factory)
    tc.add("magnet:?xt=urn:btih:A", download_dir="/data/films")
    assert captured["client"].last_download_dir == "/data/films"

    tc.add("magnet:?xt=urn:btih:B")
    assert captured["client"].last_download_dir is None
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_transmission.py -q -k download_dir`
Expected: FAIL — `TypeError: add() got an unexpected keyword argument 'download_dir'`

- [ ] **Step 3 : Implémenter**

Dans `torsearch/transmission/client.py`, remplacer `add` :

```python
    def add(self, download_url: str, download_dir: str | None = None) -> int:
        torrent = self._get_client().add_torrent(download_url, download_dir=download_dir)
        return torrent.id
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_transmission.py -q`
Expected: PASS (anciens + download_dir)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/transmission/client.py tests/test_transmission.py
git commit -m "feat: TransmissionClient.add accepts a download_dir"
```

---

## Task 3 : Auto-grab — dossier par catégorie

**Files:** Modify `torsearch/monitor/runner.py` ; Test `tests/test_monitor_runner.py`

- [ ] **Step 1 : Fake + tests**

Dans `tests/test_monitor_runner.py`, remplacer la classe `FakeTransmission` par :

```python
class FakeTransmission:
    def __init__(self):
        self.added = []
        self.dirs = []

    def add(self, url, download_dir=None):
        self.added.append(url)
        self.dirs.append(download_dir)
        return 1
```

Ajouter ces tests (à la fin du fichier) :

```python
async def test_movie_cycle_uses_movies_path(tmp_path):
    from torsearch.config import PathsConfig
    lib = _lib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), paths=PathsConfig(by_category={"movies": "/data/films"}))
    tr = FakeTransmission()
    await run_movie_cycle(cfg, lib, FakeSearch([_r("Dune.2024.1080p", infohash="X")]),
                          tr, MonitorHistory(tmp_path / "m.json"))
    assert tr.dirs == ["/data/films"]


async def test_series_cycle_uses_tv_path(tmp_path):
    from torsearch.config import PathsConfig
    lib = _slib(tmp_path)
    cfg = Config(monitor=MonitorConfig(enabled=True), paths=PathsConfig(by_category={"tv": "/data/series"}))
    tr = FakeTransmission()
    await run_series_cycle(cfg, lib, FakeSearch([_r("Show.S01E01.1080p", infohash="A")]),
                           tr, MonitorHistory(tmp_path / "m.json"))
    assert tr.dirs == ["/data/series"]
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_monitor_runner.py -q -k "movies_path or tv_path"`
Expected: FAIL — `assert [None] == ["/data/films"]` (download_dir pas encore passé)

- [ ] **Step 3 : Implémenter**

Dans `torsearch/monitor/runner.py`, dans `run_movie_cycle`, remplacer
`transmission.add(pick.download_url)` par :

```python
            transmission.add(pick.download_url, download_dir=config.paths.for_category(Category.MOVIES))
```

Dans `run_series_cycle`, remplacer `transmission.add(r.download_url)` par :

```python
            transmission.add(r.download_url, download_dir=config.paths.for_category(Category.TV))
```

(`Category` est déjà importé dans `runner.py`.)

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_monitor_runner.py -q`
Expected: PASS (anciens — qui n'assertent que `.added` — + 2 nouveaux)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/monitor/runner.py tests/test_monitor_runner.py
git commit -m "feat: auto-grab places torrents in the per-category folder"
```

---

## Task 4 : Envoi manuel — `/download` résout la catégorie

**Files:** Modify `torsearch/web/routes.py`, `torsearch/web/templates/partials/results.html` ; Test `tests/test_web.py`

- [ ] **Step 1 : Fake + test**

Dans `tests/test_web.py`, remplacer la classe `FakeTransmission` par :

```python
class FakeTransmission:
    def __init__(self):
        self.added = []
        self.dirs = []

    def add(self, download_url, download_dir=None):
        self.added.append(download_url)
        self.dirs.append(download_dir)
        return 7
```

Ajouter ce test (à la fin du fichier) :

```python
def test_download_routes_to_category_path():
    from torsearch.config import PathsConfig

    service = SearchService([FakeIndexer("t1", [])])
    transmission = FakeTransmission()
    config = Config(indexers=[IndexerConfig(name="t1", url="https://t1/api", api_key="k")],
                    paths=PathsConfig(by_category={"movies": "/data/films"}))
    client = TestClient(create_app(FakeContext(service, transmission, config)))
    resp = client.post("/download", data={"download_url": "magnet:?x", "category": "movies"})
    assert resp.status_code == 200
    assert transmission.dirs == ["/data/films"]
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_web.py -q -k "routes_to_category"`
Expected: FAIL — `assert [None] == ["/data/films"]` (route ignore la catégorie)

- [ ] **Step 3 : Route `/download`**

Dans `torsearch/web/routes.py`, remplacer la fonction `download` :

```python
@router.post("/download", response_class=HTMLResponse)
async def download(request: Request, download_url: str = Form(...), category: str = Form("")):
    ctx: AppContext = request.app.state.ctx
    try:
        cat = Category(category)
    except ValueError:
        cat = Category.OTHER
    try:
        torrent_id = ctx.transmission.add(download_url, ctx.config.paths.for_category(cat))
        message, ok = f"Ajoute a Transmission (#{torrent_id})", True
    except Exception as exc:
        message, ok = f"Erreur Transmission : {exc}", False
    return templates.TemplateResponse(request, "partials/toast.html", {"ok": ok, "message": message})
```

- [ ] **Step 4 : Formulaire « Envoyer »**

Dans `torsearch/web/templates/partials/results.html`, dans le formulaire `hx-post="/download"`,
juste après `<input type="hidden" name="download_url" value="{{ r.download_url }}">`, ajouter :

```html
      <input type="hidden" name="category" value="{{ r.category.value }}">
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_web.py -q`
Expected: PASS (anciens + routing par catégorie)

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/routes.py torsearch/web/templates/partials/results.html tests/test_web.py
git commit -m "feat: manual download routes to the result's category folder"
```

---

## Task 5 : Réglages — section « Dossiers de téléchargement »

**Files:** Modify `torsearch/settings/mutations.py`, `torsearch/web/settings_routes.py`, `torsearch/web/templates/settings.html` ; Test `tests/test_settings_web.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_settings_web.py` :

```python
def test_update_paths(tmp_path):
    from fastapi.testclient import TestClient

    from torsearch.context import AppContext
    from torsearch.models import Category
    from torsearch.settings.store import SettingsStore
    from torsearch.web.routes import create_app

    ctx = AppContext(SettingsStore(str(tmp_path / "s.json")))
    client = TestClient(create_app(ctx))
    resp = client.post("/settings/paths", data={"path_movies": "/data/films", "path_tv": "/data/series", "path_anime": ""})
    assert resp.status_code == 200
    assert ctx.config.paths.for_category(Category.MOVIES) == "/data/films"
    assert ctx.config.paths.for_category(Category.TV) == "/data/series"
    assert ctx.config.paths.for_category(Category.ANIME) is None
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_settings_web.py -q -k update_paths`
Expected: FAIL — `404 Not Found` pour `/settings/paths`

- [ ] **Step 3 : Mutation `set_paths`**

Dans `torsearch/settings/mutations.py`, ajouter `PathsConfig` à l'import depuis `torsearch.config`,
puis ajouter à la fin :

```python
def set_paths(config: Config, paths: PathsConfig) -> Config:
    return config.model_copy(update={"paths": paths})
```

- [ ] **Step 4 : Route + contexte Réglages**

Dans `torsearch/web/settings_routes.py` :
- ajouter `PathsConfig` à l'import depuis `torsearch.config`, `set_paths` à l'import depuis
  `torsearch.settings.mutations`, et ajouter `from torsearch.models import Category`.
- dans `settings_page`, ajouter `"categories": list(Category)` au contexte du `TemplateResponse`.
- ajouter la route à la fin du fichier :

```python
@settings_router.post("/settings/paths", response_class=HTMLResponse)
async def update_paths(request: Request):
    ctx: AppContext = request.app.state.ctx
    form = await request.form()
    by_category = {}
    for c in Category:
        if c == Category.ALL:
            continue
        value = (form.get(f"path_{c.value}") or "").strip()
        if value:
            by_category[c.value] = value
    try:
        ctx.update_settings(set_paths(ctx.config, PathsConfig(by_category=by_category)))
        return _toast(request, True, "Dossiers enregistres.")
    except (ValidationError, SettingsError) as exc:
        return _toast(request, False, f"Erreur : {exc}")
```

- [ ] **Step 5 : Section Réglages**

Dans `torsearch/web/templates/settings.html`, avant `{% endblock %}`, ajouter :

```html
<section class="mt-10">
  <h2 class="font-semibold mb-2">Dossiers de telechargement</h2>
  <p class="text-xs text-slate-500 mb-2">Chemins vus par Transmission (dans son conteneur le cas echeant). Vide = dossier par defaut.</p>
  <form hx-post="/settings/paths" hx-target="#toast" class="flex flex-wrap items-end gap-3">
    {% for c in categories %}{% if c.value != 'all' %}
    <label class="text-xs text-slate-400">{{ c.value | capitalize }}<br>
      <input name="path_{{ c.value }}" value="{{ config.paths.by_category.get(c.value, '') }}" placeholder="/data/{{ c.value }}" class="mt-1 w-48 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    {% endif %}{% endfor %}
    <button class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-4 py-2">Enregistrer</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 6 : Vérifier le succès**

Run: `uv run pytest tests/test_settings_web.py -q`
Expected: PASS

- [ ] **Step 7 : Commit**

```bash
git add torsearch/settings/mutations.py torsearch/web/settings_routes.py torsearch/web/templates/settings.html tests/test_settings_web.py
git commit -m "feat: configure per-category download folders in settings"
```

---

## Task 6 : Vérification finale

- [ ] **Step 1 : Toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante (240) + nouveaux (config paths, transmission download_dir, cycles, /download routing, settings paths), aucune régression.

- [ ] **Step 2 : Vérif visuelle (optionnel, manuel)**

Réglages → renseigner Films `/data/films` et Séries `/data/series` ; envoyer un résultat film
depuis la recherche → vérifier dans Transmission qu'il atterrit dans `/data/films`.

---

## Self-review (notes)

- **Couverture spec :** `PathsConfig`+`for_category` (T1), `add(download_dir)` (T2), cycles
  auto-grab (T3), `/download` + `results.html` (T4), mutation + route + Réglages génériques (T5),
  non-régression (T6). ✔
- **Cohérence des noms :** `PathsConfig.by_category` / `for_category`, `set_paths`,
  `TransmissionClient.add(download_url, download_dir)`, route `/settings/paths`, champ form
  `category` / `path_<cat>`, `FakeTransmission.dirs`. ✔
- **Pas de placeholder :** code/markup/commandes exacts.
- **Non-régression fakes :** les `FakeTransmission`/`FakeRpc` gardent `.added` (urls) pour les
  assertions existantes, et ajoutent `.dirs`/`last_download_dir` pour les nouvelles.
