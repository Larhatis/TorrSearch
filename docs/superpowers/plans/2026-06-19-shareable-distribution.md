# Distribution — rendre TorSearch partageable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre TorSearch « clone-and-run » : un `docker compose up` lance TorSearch + Transmission pré-câblés, l'app démarre vide et se configure dans l'UI ; README public, licence MIT, onboarding état-vide, CI.

**Architecture:** Surtout des fichiers de packaging/docs (compose, bootstrap, README, LICENSE, CI). Un seul changement de code : la page de recherche affiche une invitation quand aucun tracker n'est configuré. Aucun secret versionné.

**Tech Stack:** Docker Compose · GitHub Actions · FastAPI/Jinja (onbording) · pytest.

**Base :** branche `feat/shareable` (sur `main`). Commandes via `.venv/bin/python -m pytest ...`. Code existant : `torsearch/web/routes.py` (route `GET /` rend `index.html` avec `{"categories": ...}`, `create_app(ctx)`, `ctx.config.indexers`), `torsearch/web/templates/index.html`, `Dockerfile` (python:3.12-slim, `uvicorn torsearch.main:get_app --factory`), `pyproject.toml` (extra `dev` = pytest/pytest-asyncio/respx). Dépôt GitHub : `Larhatis/TorrSearch`.

---

## File Structure

| Fichier | Action |
|---|---|
| `torsearch/web/routes.py` | Modifier — `GET /` passe `has_trackers`. |
| `torsearch/web/templates/index.html` | Modifier — bannière état vide. |
| `tests/test_web.py` | Modifier — tests onboarding. |
| `docker-compose.yml` | Remplacer — stack TorSearch + Transmission. |
| `deploy/bootstrap.yaml` | Créer — amorçage `transmission.host`. |
| `.gitignore` | Modifier — `+ transmission/`. |
| `README.md` | Réécrire. |
| `LICENSE` | Créer — MIT. |
| `.github/workflows/ci.yml` | Créer. |

---

## Task 1: Onboarding « état vide »

**Files:**
- Modify: `torsearch/web/routes.py`, `torsearch/web/templates/index.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_web.py`)**

```python
def test_index_shows_onboarding_when_no_trackers():
    service = SearchService([])
    ctx = FakeContext(service, FakeTransmission(), Config())  # no indexers
    client = TestClient(create_app(ctx))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Aucun tracker configure" in resp.text
    assert "/settings" in resp.text


def test_index_hides_onboarding_when_trackers_present():
    client, _ = _make()  # _make() seeds one indexer "t1"
    resp = client.get("/")
    assert "Aucun tracker configure" not in resp.text
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web.py -k onboarding -v`
Expected: FAIL — the onboarding banner is not rendered yet.

- [ ] **Step 3: Pass `has_trackers` from the `/` route**

In `torsearch/web/routes.py`, replace the `index` handler with:
```python
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx: AppContext = request.app.state.ctx
    return templates.TemplateResponse(
        request,
        "index.html",
        {"categories": list(Category), "has_trackers": bool(ctx.config.indexers)},
    )
```

- [ ] **Step 4: Add the banner to `index.html`**

In `torsearch/web/templates/index.html`, immediately after the `{% block content %}` line, insert:
```html
{% if not has_trackers %}
<div class="mb-4 rounded border border-amber-600/40 bg-amber-600/10 px-4 py-3 text-sm">
  👉 Aucun tracker configure. <a href="/settings" class="underline text-amber-300 hover:text-amber-200">Ajoute tes trackers dans Reglages</a> pour commencer.
</div>
{% endif %}
```

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: PASS — the 2 onboarding tests + all pre-existing web tests (the search form still renders, `_make()`-based tests unaffected since they seed a tracker).

- [ ] **Step 6: Commit**

```bash
git add torsearch/web/routes.py torsearch/web/templates/index.html tests/test_web.py
git commit -m "feat: show onboarding hint on search page when no trackers configured"
```

---

## Task 2: Docker compose stack + amorçage Transmission

**Files:**
- Replace: `docker-compose.yml`
- Create: `deploy/bootstrap.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: Create `deploy/bootstrap.yaml`**

```yaml
# Amorcage au premier demarrage uniquement : pre-cable TorSearch sur le service Transmission
# du docker-compose. Ensuite, toute la config se fait dans /settings (data/settings.json).
transmission:
  host: transmission
  port: 9091
```

- [ ] **Step 2: Replace `docker-compose.yml` with**

```yaml
services:
  torsearch:
    build: .
    container_name: torsearch
    ports:
      - "8080:8000"
    environment:
      - TORSEARCH_SETTINGS=/data/settings.json
      - TORSEARCH_MONITOR=/data/monitor.json
      - TORSEARCH_CONFIG=/bootstrap/bootstrap.yaml
    volumes:
      - ./data:/data
      - ./deploy/bootstrap.yaml:/bootstrap/bootstrap.yaml:ro
    depends_on:
      - transmission
    restart: unless-stopped

  transmission:
    image: lscr.io/linuxserver/transmission:latest
    container_name: transmission
    ports:
      - "9091:9091"
      - "51413:51413"
      - "51413:51413/udp"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
    volumes:
      - ./transmission/config:/config
      - ./transmission/downloads:/downloads
    restart: unless-stopped
```

- [ ] **Step 3: Ignore the Transmission data dir**

In `.gitignore`, under the `# Secrets / config locale` section, add a line:
```
transmission/
```

- [ ] **Step 4: Validate the compose file**

Run: `docker compose config -q`
Expected: no output, exit code 0 (the compose YAML is valid). If `docker` is unavailable in the environment, instead run `.venv/bin/python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); yaml.safe_load(open('deploy/bootstrap.yaml')); print('yaml OK')"` and expect `yaml OK`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml deploy/bootstrap.yaml .gitignore
git commit -m "feat: full-stack docker-compose with bundled pre-wired Transmission"
```

---

## Task 3: README, LICENSE et CI

**Files:**
- Replace: `README.md`
- Create: `LICENSE`, `.github/workflows/ci.yml`

- [ ] **Step 1: Replace `README.md` with**

````markdown
# TorSearch

![CI](https://github.com/Larhatis/TorrSearch/actions/workflows/ci.yml/badge.svg)

Recherche un film ou une serie sur **plusieurs trackers Torznab a la fois** et envoie le
resultat choisi a **Transmission** — depuis une interface web. Une alternative legere et
auto-hebergee a Prowlarr/Jackett + Sonarr/Radarr, a configurer entierement au clic.

## Fonctionnalites

- 🔎 **Recherche multi-trackers** Torznab, en parallele, fusionnee et dedoublonnee.
- 🎛️ **Tout se configure dans l'UI** (page Reglages) : trackers, connexion Transmission — rien a coder.
- 🧰 **Filtres & tri** : seeders, taille, qualite (4K/1080p…), exclusion de mots ; colonnes triables.
- ⬇️ **Envoi a Transmission** en un clic + page **Telechargements** (suivi en direct, pause/reprise/suppression).
- 🛰️ **Surveillance auto** : recherches sauvegardees qui tournent en fond et envoient (ou signalent) les nouveaux resultats.

## Demarrage rapide (Docker)

Pre-requis : Docker + Docker Compose.

```bash
git clone https://github.com/Larhatis/TorrSearch.git
cd TorrSearch
docker compose up -d
```

Ouvre **http://localhost:8080**. L'app demarre **vide** : va dans **Reglages** pour ajouter tes
trackers (URL Torznab + passkey). Transmission est inclus dans le compose et deja branche.

> Tu as deja ton propre Transmission ? Dans **Reglages → Transmission**, remplace l'hote
> `transmission` par l'adresse de ton instance (et retire le service `transmission` du
> `docker-compose.yml` si tu n'en veux pas).

## Configuration

- **Trackers** : Reglages → ajoute un tracker Torznab (nom, URL, passkey). Le bouton **Tester** verifie que ca repond.
- **Transmission** : Reglages → hote / port / identifiants.
- Toute la config est persistee dans `data/settings.json` (volume, jamais versionne).

## Developpement

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn torsearch.main:get_app --factory --reload   # http://localhost:8000
```

## Avertissement

TorSearch est un outil de **recherche et d'agregation** (comme Prowlarr/Jackett). Il ne fournit
aucun contenu. L'usage que tu en fais, le respect du droit d'auteur et des regles des trackers
relevent de **ta** responsabilite et des lois de ton pays.

## Licence

[MIT](LICENSE) — contributions bienvenues (ouvre une issue ou une PR).
````

- [ ] **Step 2: Create `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 Clement Cappeau

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Tests
        run: pytest
```

- [ ] **Step 4: Sanity-check the new files**

Run:
```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci yaml OK')"
test -f LICENSE && grep -q 'MIT License' LICENSE && echo 'LICENSE OK'
grep -q 'docker compose up' README.md && echo 'README OK'
```
Expected: `ci yaml OK`, `LICENSE OK`, `README OK`.

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (the onboarding change from Task 1 included).

- [ ] **Step 6: Commit**

```bash
git add README.md LICENSE .github/workflows/ci.yml
git commit -m "docs: public README, MIT license and GitHub Actions CI"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. `docker compose up -d --build` sur une machine propre → ouvrir `http://localhost:8080` :
   l'app démarre, affiche l'invitation « Ajoute tes trackers », et la page Téléchargements voit
   le Transmission embarqué (liste vide, pas d'erreur).
2. Après `git push`, vérifier que le workflow **CI** apparaît vert dans l'onglet Actions de GitHub
   et que le badge du README s'affiche.
3. Ajouter ensuite (optionnel) 1-2 captures d'écran dans le README depuis l'app lancée.
