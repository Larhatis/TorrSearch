# Redesign UI Phase 1 (shell + Recherche) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre le shell partagé (`base.html`) et l'écran Recherche pour une UI plus ergonomique (nav à icônes + état actif, barre de recherche unifiée, filtres en puces actives + panneau, lignes de résultat scannables avec badge qualité et santé des seeders), sans build step.

**Architecture:** Macros Jinja réutilisables (`partials/components.html`) + `detect_quality` exposé en global Jinja ; `base.html` devient le shell commun ; `index.html`/`partials/results.html` restylés ; `/search` enrichit le contexte avec `active_filters` + `sources`. Contrat des query params inchangé.

**Tech Stack:** FastAPI/Starlette, Jinja2, Tailwind Play CDN, HTMX, Tabler Icons (webfont CDN), pytest + `TestClient`.

**Spec :** `docs/superpowers/specs/2026-06-20-ui-redesign-phase1-design.md`

---

## Structure des fichiers

- **Modifier** `torsearch/web/templating.py` — enregistrer `detect_quality` comme global Jinja.
- **Créer** `torsearch/web/templates/partials/components.html` — macros `badge_quality`, `health`, `source_chip`.
- **Créer** `tests/test_components.py` — tests des macros via l'env Jinja.
- **Modifier** `torsearch/web/templates/base.html` — shell : en-tête collant, nav à icônes + `aria-current`, Tabler Icons, bouton Déconnexion préservé.
- **Modifier** `torsearch/web/templates/index.html` — barre de recherche unifiée, panneau filtres, helper JS `clearFilter`.
- **Modifier** `torsearch/web/routes.py` — `_active_filters` + contexte `active_filters`/`sources` pour `/search`.
- **Modifier** `torsearch/web/templates/partials/results.html` — barre d'outils + tri, puces de filtres actifs, lignes de résultat via macros.
- **Modifier** `tests/test_web.py` — mettre à jour le test des en-têtes triables, ajouter tests (badge, santé, puces, compteur, nav active).

---

## Task 1 : global `detect_quality` + macros `components.html`

**Files:**
- Modify: `torsearch/web/templating.py`
- Create: `torsearch/web/templates/partials/components.html`
- Test: `tests/test_components.py`

- [ ] **Step 1 : Écrire les tests des macros**

Créer `tests/test_components.py` :

```python
from torsearch.web.templating import templates


def _render(call: str) -> str:
    src = (
        "{% from 'partials/components.html' import badge_quality, health, source_chip %}"
        + call
    )
    return templates.env.from_string(src).render()


def test_health_good_ok_low():
    assert 'data-health="good"' in _render("{{ health(150) }}")
    assert 'data-health="ok"' in _render("{{ health(40) }}")
    assert 'data-health="low"' in _render("{{ health(5) }}")
    assert ">5<" in _render("{{ health(5) }}")


def test_badge_quality_labels():
    out = _render("{{ badge_quality('Film.2024.1080p.WEB') }}")
    assert 'data-quality="1080p"' in out
    assert "1080p" in out
    assert 'data-quality="2160p"' in _render("{{ badge_quality('Film 2160p UHD') }}")
    assert 'data-quality="other"' in _render("{{ badge_quality('Film DVDRip') }}")


def test_source_chip_shows_name():
    assert "torr9" in _render("{{ source_chip('torr9') }}")
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_components.py -q`
Expected: FAIL — `TemplateNotFound: partials/components.html` (et `detect_quality` non défini)

- [ ] **Step 3 : Enregistrer le global `detect_quality`**

Remplacer le contenu de `torsearch/web/templating.py` par :

```python
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from torsearch.search.filters import detect_quality

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _auth_context(request):
    auth = getattr(request.app.state, "auth", None)
    return {"auth_enabled": bool(auth and getattr(auth, "enabled", False))}


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_auth_context])
templates.env.globals["detect_quality"] = detect_quality
```

- [ ] **Step 4 : Créer les macros**

Créer `torsearch/web/templates/partials/components.html` :

```html
{% macro badge_quality(title) %}
{%- set q = detect_quality(title) -%}
{%- set cls = {'2160p': 'bg-violet-500/15 text-violet-300', '1080p': 'bg-sky-500/15 text-sky-300', '720p': 'bg-slate-700 text-slate-300', '480p': 'bg-slate-700 text-slate-400', 'other': 'bg-slate-800 text-slate-500'} -%}
<span data-quality="{{ q }}" class="rounded px-1.5 py-0.5 text-[11px] {{ cls[q] }}">{{ q }}</span>
{%- endmacro %}

{% macro health(seeders) %}
{%- set level = 'good' if seeders >= 100 else ('ok' if seeders >= 10 else 'low') -%}
{%- set txt = {'good': 'text-emerald-400', 'ok': 'text-amber-400', 'low': 'text-red-400'} -%}
{%- set dot = {'good': 'bg-emerald-500', 'ok': 'bg-amber-500', 'low': 'bg-red-500'} -%}
<span data-health="{{ level }}" class="inline-flex items-center justify-end gap-1.5 {{ txt[level] }}"><span class="h-1.5 w-1.5 rounded-full {{ dot[level] }}"></span>{{ seeders }}</span>
{%- endmacro %}

{% macro source_chip(source) %}
<span class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-400">{{ source }}</span>
{%- endmacro %}
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_components.py -q`
Expected: PASS (3 tests)

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/templating.py torsearch/web/templates/partials/components.html tests/test_components.py
git commit -m "feat: add Jinja components (quality badge, seeder health, source chip)"
```

---

## Task 2 : Shell `base.html` (nav à icônes + état actif)

**Files:**
- Modify: `torsearch/web/templates/base.html`
- Test: `tests/test_web.py`

- [ ] **Step 1 : Écrire les tests d'état actif de la nav**

Ajouter en tête de `tests/test_web.py` l'import `re` (après `from fastapi.testclient import TestClient`) :

```python
import re
```

Ajouter ces tests à la fin de `tests/test_web.py` :

```python
def test_nav_marks_search_active():
    client, _ = _make()
    html = client.get("/").text
    assert re.search(r'href="/"[^>]*aria-current="page"', html)


def test_nav_marks_downloads_active():
    client, _ = _make()
    html = client.get("/downloads").text
    assert re.search(r'href="/downloads"[^>]*aria-current="page"', html)


def test_nav_keeps_logout_hidden_when_auth_disabled():
    client, _ = _make()
    assert "Deconnexion" not in client.get("/").text
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_web.py -q -k "nav_marks"`
Expected: FAIL — `aria-current` absent du markup actuel

- [ ] **Step 3 : Remplacer `base.html`**

Remplacer tout le contenu de `torsearch/web/templates/base.html` par :

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TorrSearch</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3/dist/tabler-icons.min.css">
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
  {% set path = request.url.path %}
  <header class="sticky top-0 z-10 flex items-center gap-6 border-b border-slate-800 bg-slate-900/95 px-6 py-3 backdrop-blur">
    <a href="/" class="flex items-center gap-2 text-lg font-bold text-emerald-400"><i class="ti ti-windmill"></i>TorrSearch</a>
    <nav class="flex gap-1 text-sm">
      <a href="/" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path == '/' %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path == '/' %} aria-current="page"{% endif %}><i class="ti ti-search"></i>Recherche</a>
      <a href="/settings" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path.startswith('/settings') %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path.startswith('/settings') %} aria-current="page"{% endif %}><i class="ti ti-settings"></i>Reglages</a>
      <a href="/downloads" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path.startswith('/downloads') %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path.startswith('/downloads') %} aria-current="page"{% endif %}><i class="ti ti-download"></i>Telechargements</a>
      <a href="/surveillance" class="flex items-center gap-1.5 rounded px-2.5 py-1.5 {% if path.startswith('/surveillance') %}text-emerald-400{% else %}text-slate-300 hover:text-emerald-400{% endif %}"{% if path.startswith('/surveillance') %} aria-current="page"{% endif %}><i class="ti ti-eye"></i>Surveillance</a>
    </nav>
    {% if auth_enabled %}
    <form method="post" action="/logout" class="ml-auto">
      <button type="submit" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-emerald-400"><i class="ti ti-logout"></i>Deconnexion</button>
    </form>
    {% endif %}
  </header>
  <main class="max-w-5xl mx-auto px-6 py-8">
    {% block content %}{% endblock %}
  </main>
  <div id="toast" class="fixed bottom-4 right-4"></div>
</body>
</html>
```

- [ ] **Step 4 : Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_web.py -q -k "nav_marks or logout_hidden"`
Expected: PASS (3 tests)

- [ ] **Step 5 : Non-régression du fichier web**

Run: `uv run pytest tests/test_web.py tests/test_auth.py -q`
Expected: PASS (le bouton Déconnexion conditionnel et `auth_enabled` restent intacts)

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/templates/base.html tests/test_web.py
git commit -m "feat: redesign shared shell with icon nav and active state"
```

---

## Task 3 : Barre de recherche + panneau filtres (`index.html`)

**Files:**
- Modify: `torsearch/web/templates/index.html`
- Test: `tests/test_web.py`

- [ ] **Step 1 : Écrire les tests de l'écran de recherche**

Ajouter à la fin de `tests/test_web.py` :

```python
def test_index_has_filter_panel_fields():
    client, _ = _make()
    html = client.get("/").text
    assert 'name="min_seeders"' in html
    assert 'name="quality"' in html
    assert 'name="exclude"' in html


def test_index_defines_clear_filter_helper():
    client, _ = _make()
    assert "function clearFilter" in client.get("/").text
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_web.py -q -k "filter_panel or clear_filter"`
Expected: FAIL — `function clearFilter` absent (le reste peut déjà passer)

- [ ] **Step 3 : Remplacer `index.html`**

Remplacer tout le contenu de `torsearch/web/templates/index.html` par :

```html
{% extends "base.html" %}
{% block content %}
{% if not has_trackers %}
<div class="mb-5 rounded-lg border border-amber-600/40 bg-amber-600/10 px-4 py-3 text-sm">
  <i class="ti ti-alert-triangle text-amber-400"></i> Aucun tracker configure. <a href="/settings" class="underline text-amber-300 hover:text-amber-200">Ajoute tes trackers dans Reglages</a> pour commencer.
</div>
{% endif %}
<form id="search-form" hx-get="/search" hx-target="#results" hx-indicator="#spinner" class="mb-5">
  <div class="flex items-stretch overflow-hidden rounded-xl border border-slate-700 bg-slate-800 focus-within:border-emerald-500">
    <span class="flex items-center pl-4 text-slate-500"><i class="ti ti-search text-lg"></i></span>
    <input type="text" name="q" placeholder="Rechercher un film, une serie..." autofocus
           class="min-w-0 flex-1 bg-transparent px-3 py-3 text-slate-100 outline-none">
    <select name="cat" class="border-l border-slate-700 bg-transparent px-3 text-sm text-slate-300 outline-none">
      {% for c in categories %}
      <option value="{{ c.value }}" class="bg-slate-800">{{ c.value | capitalize }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="bg-emerald-500 px-5 font-semibold text-slate-900 hover:bg-emerald-400">Chercher</button>
    <span id="spinner" class="htmx-indicator flex items-center px-3 text-sm text-slate-400">...</span>
  </div>
  <details class="group mt-3 text-sm">
    <summary class="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 hover:border-slate-600">
      <i class="ti ti-filter"></i> Filtres <i class="ti ti-chevron-down text-xs transition-transform group-open:rotate-180"></i>
    </summary>
    <div class="mt-3 flex flex-wrap items-end gap-4 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <label class="text-xs text-slate-400">Seeders min<br>
        <input type="number" name="min_seeders" value="0" min="0" class="mt-1 w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille min (Go)<br>
        <input type="number" name="min_size_gb" step="0.1" min="0" class="mt-1 w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille max (Go)<br>
        <input type="number" name="max_size_gb" step="0.1" min="0" class="mt-1 w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1"></label>
      <fieldset class="text-xs text-slate-400">
        <legend>Qualite</legend>
        <div class="mt-1 flex gap-2">
          {% for qv in ["2160p", "1080p", "720p", "480p", "other"] %}
          <label class="flex items-center gap-1"><input type="checkbox" name="quality" value="{{ qv }}"> {{ qv }}</label>
          {% endfor %}
        </div>
      </fieldset>
      <label class="text-xs text-slate-400">Exclure ces mots<br>
        <input type="text" name="exclude" placeholder="cam, ts, multi" class="mt-1 w-48 rounded border border-slate-700 bg-slate-800 px-2 py-1"></label>
    </div>
  </details>
</form>
<div id="results"></div>
<script>
function clearFilter(name, value) {
  const form = document.getElementById('search-form');
  if (!form) return;
  if (name === 'quality' && value) {
    form.querySelectorAll('input[name="quality"]').forEach(function (cb) {
      if (cb.value === value) cb.checked = false;
    });
  } else if (name === 'min_seeders') {
    const el = form.querySelector('[name="min_seeders"]');
    if (el) el.value = '0';
  } else {
    const el = form.querySelector('[name="' + name + '"]');
    if (el) el.value = '';
  }
  htmx.trigger(form, 'submit');
}
</script>
{% endblock %}
```

- [ ] **Step 4 : Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_web.py -q -k "filter_panel or clear_filter or onboarding or search_form"`
Expected: PASS (les tests d'onboarding et `name="q"` restent verts)

- [ ] **Step 5 : Commit**

```bash
git add torsearch/web/templates/index.html tests/test_web.py
git commit -m "feat: unified search bar and collapsible filter panel"
```

---

## Task 4 : Résultats restylés + `active_filters` (`results.html` + route)

**Files:**
- Modify: `torsearch/web/routes.py`
- Modify: `torsearch/web/templates/partials/results.html`
- Test: `tests/test_web.py`

- [ ] **Step 1 : Mettre à jour / ajouter les tests résultats**

Dans `tests/test_web.py`, remplacer le test existant `test_search_renders_sortable_headers` par :

```python
def test_search_renders_sort_control():
    client, _ = _make([_result("Anything")])
    resp = client.get("/search", params={"q": "x"})
    assert "hx-vals" in resp.text
    assert "Seeders" in resp.text
```

Puis ajouter à la fin de `tests/test_web.py` :

```python
def test_search_renders_quality_badge():
    client, _ = _make([_result("Film.2024.1080p.WEB")])
    resp = client.get("/search", params={"q": "x"})
    assert 'data-quality="1080p"' in resp.text


def test_search_renders_seeder_health():
    client, _ = _make([_result("Healthy", seeders=150), _result("Weak", seeders=5)])
    resp = client.get("/search", params={"q": "x"})
    assert 'data-health="good"' in resp.text
    assert 'data-health="low"' in resp.text


def test_search_shows_result_count():
    client, _ = _make([_result("One"), _result("Two")])
    resp = client.get("/search", params={"q": "x"})
    assert "2 resultat" in resp.text.lower()


def test_search_renders_active_filter_chip():
    client, _ = _make([_result("KeepMe", seeders=80)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "10"})
    assert 'data-filter="min_seeders"' in resp.text
    assert "clearFilter('min_seeders')" in resp.text
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_web.py -q -k "sort_control or quality_badge or seeder_health or result_count or active_filter"`
Expected: FAIL — nouveau markup absent

- [ ] **Step 3 : Ajouter `_active_filters` + contexte dans la route**

Dans `torsearch/web/routes.py`, ajouter cette fonction juste avant `@router.get("/search"...)` :

```python
def _active_filters(filters: ResultFilters) -> list[dict]:
    chips: list[dict] = []
    if filters.min_seeders > 0:
        chips.append({"label": f"Seeders ≥ {filters.min_seeders}", "name": "min_seeders"})
    if filters.min_size is not None:
        chips.append({"label": f"≥ {round(filters.min_size / _GB, 1)} Go", "name": "min_size_gb"})
    if filters.max_size is not None:
        chips.append({"label": f"≤ {round(filters.max_size / _GB, 1)} Go", "name": "max_size_gb"})
    for q in filters.qualities:
        chips.append({"label": q, "name": "quality", "value": q})
    if filters.exclude:
        chips.append({"label": "exclut : " + ", ".join(filters.exclude), "name": "exclude"})
    return chips
```

Dans la fonction `search`, remplacer le `return templates.TemplateResponse(...)` final par :

```python
    sources = [ix.name for ix in ctx.config.indexers if ix.enabled]
    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "results": results,
            "query": q,
            "sort": effective_sort,
            "dir": effective_dir,
            "active_filters": _active_filters(filters),
            "sources": sources,
        },
    )
```

- [ ] **Step 4 : Remplacer `partials/results.html`**

Remplacer tout le contenu de `torsearch/web/templates/partials/results.html` par :

```html
{% from "partials/components.html" import badge_quality, health, source_chip %}
{% if not results %}
  <p class="text-slate-400">Aucun resultat{% if query %} pour "{{ query }}"{% endif %}.</p>
{% else %}
<div class="mb-3 flex items-center justify-between text-sm">
  <span class="text-slate-400"><span class="text-slate-100">{{ results | length }} resultat{{ 's' if results | length > 1 else '' }}</span>{% if sources %} &middot; {{ sources | join(', ') }}{% endif %}</span>
  <span class="flex items-center gap-2">
    <select name="sort" hx-get="/search" hx-include="#search-form" hx-target="#results"
            class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300">
      {% for val, lbl in [('seeders', 'Seeders'), ('size', 'Taille'), ('date', 'Date'), ('title', 'Nom')] %}
      <option value="{{ val }}" {% if sort == val %}selected{% endif %}>{{ lbl }}</option>
      {% endfor %}
    </select>
    <button hx-get="/search" hx-include="#search-form" hx-target="#results"
            hx-vals='{"sort": "{{ sort }}", "dir": "{{ 'asc' if dir == 'desc' else 'desc' }}"}'
            class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:text-emerald-400"
            aria-label="Inverser le sens du tri"><i class="ti ti-arrow-{{ 'down' if dir == 'desc' else 'up' }}"></i></button>
  </span>
</div>
{% if active_filters %}
<div class="mb-3 flex flex-wrap items-center gap-2">
  {% for f in active_filters %}
  <button type="button" data-filter="{{ f.name }}"
          onclick="clearFilter('{{ f.name }}'{% if f.value is defined and f.value %}, '{{ f.value }}'{% endif %})"
          class="inline-flex items-center gap-1.5 rounded-full border border-emerald-700/60 bg-emerald-900/20 px-2.5 py-1 text-xs text-emerald-200">
    {{ f.label }} <i class="ti ti-x text-[13px]"></i>
  </button>
  {% endfor %}
</div>
{% endif %}
<div class="flex flex-col gap-1.5">
  {% for r in results %}
  <div class="flex items-center gap-4 rounded-lg border border-slate-800 px-3 py-2.5 hover:bg-slate-800/40{% if r.seeders < 10 %} opacity-75{% endif %}">
    <div class="min-w-0 flex-1">
      <div class="truncate text-sm text-slate-100">{{ r.title }}</div>
      <div class="mt-1 flex items-center gap-2">
        {{ badge_quality(r.title) }}
        {{ source_chip(r.source) }}
        <span class="whitespace-nowrap text-[11px] text-slate-500"><i class="ti ti-calendar"></i> {{ r.publish_date.strftime('%d/%m/%Y') if r.publish_date else '-' }}</span>
      </div>
    </div>
    <div class="w-16 whitespace-nowrap text-right text-sm text-slate-100">{{ (r.size / 1073741824) | round(2) }} Go</div>
    <div class="w-16 text-right text-sm">{{ health(r.seeders) }}</div>
    <form hx-post="/download" hx-target="#toast" class="inline">
      <input type="hidden" name="download_url" value="{{ r.download_url }}">
      <button class="flex items-center gap-1 rounded bg-emerald-500 px-2.5 py-1.5 text-xs font-semibold text-slate-900 hover:bg-emerald-400"><i class="ti ti-plus"></i>Envoyer</button>
    </form>
    <button class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-400 hover:text-emerald-400"
            aria-label="Copier le lien" onclick="navigator.clipboard.writeText('{{ r.download_url }}')"><i class="ti ti-copy"></i></button>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_web.py -q`
Expected: PASS — tous les tests de `test_web.py`, anciens (filtres, tri, download, onboarding) et nouveaux (badge, santé, compteur, puces, tri).

- [ ] **Step 6 : Commit**

```bash
git add torsearch/web/routes.py torsearch/web/templates/partials/results.html tests/test_web.py
git commit -m "feat: scannable result rows with badges, health, active filter chips"
```

---

## Task 5 : Vérification finale

- [ ] **Step 1 : Lancer toute la suite**

Run: `uv run pytest -q`
Expected: PASS — suite existante + auth + nouveaux tests, aucune régression.

- [ ] **Step 2 : Vérif visuelle rapide (optionnel, manuel)**

Run: `uv run uvicorn torsearch.main:build_app --factory --port 8000`
Puis ouvrir `http://localhost:8000/`, lancer une recherche, vérifier : nav active, barre unifiée, panneau filtres, lignes avec badges + santé, puces de filtres actifs, tri.

---

## Self-review (notes)

- **Couverture spec :** shell + nav active (Task 2), composants/`detect_quality` global (Task 1), barre de recherche + panneau filtres (Task 3), barre d'outils + tri + puces actives + lignes enrichies + `active_filters` route (Task 4), Tabler Icons (Task 2 `<head>`), tests mis à jour + nouveaux (Tasks 2-4), non-régression auth (Task 2 Step 5, Task 5). ✔
- **Cohérence des noms :** macros `badge_quality`/`health`/`source_chip`, attributs de test `data-quality`/`data-health`/`data-filter`, helper `clearFilter(name, value)`, `_active_filters(filters)`, contexte `active_filters`/`sources` — identiques entre tasks. ✔
- **Pas de placeholder :** chaque step contient le markup/code/commande exact. ✔
- **Note Tailwind Play CDN :** valeurs arbitraires (`text-[11px]`, `bg-violet-500/15`, `group-open:rotate-180`) supportées par le JIT du CDN.
