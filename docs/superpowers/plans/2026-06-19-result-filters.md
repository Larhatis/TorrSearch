# F1 — Filtres + tri des résultats — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filtrer (seeders, taille, qualité, exclusion) et trier (colonnes cliquables) les résultats de recherche, côté serveur via HTMX.

**Architecture:** Un module pur `torsearch/search/filters.py` (`detect_quality`, `ResultFilters`, `apply`) filtre/trie la liste renvoyée par `SearchService` sans le modifier. La route `/search` lit des paramètres optionnels, construit un `ResultFilters` (avec repli robuste sur les défauts), applique, et rend le tableau. Les en-têtes deviennent des liens HTMX qui re-requêtent en changeant le tri.

**Tech Stack:** Python 3.12+ (3.14 local) · FastAPI · Pydantic v2 · Jinja2 + HTMX · pytest.

**Base :** branche `feat/result-filters` (sur `main`). Commandes via `.venv/bin/python -m pytest ...`. Code existant utilisé : `torsearch/models.py` (`SearchResult` : `title, size(octets), seeders, leechers, source, category, download_url, publish_date, infohash`), `torsearch/web/routes.py` (route `/search`, `create_app(ctx)`, `templates` importé de `torsearch.web.templating`), templates `index.html` + `partials/results.html`.

---

## File Structure

| Fichier | Action |
|---|---|
| `torsearch/search/filters.py` | Créer — `detect_quality`, `ResultFilters`, `apply`, constantes `VALID_SORTS`/`VALID_DIRECTIONS`. |
| `tests/test_filters.py` | Créer. |
| `torsearch/web/routes.py` | Modifier — `/search` parse filtres + tri, applique `filters.apply`. |
| `torsearch/web/templates/index.html` | Modifier — `id="search-form"` + panneau « Filtres ». |
| `torsearch/web/templates/partials/results.html` | Modifier — en-têtes triables + colonne Date. |
| `tests/test_web.py` | Modifier — cas filtrage/tri. |

---

## Task 1: Module de filtres et tri

**Files:**
- Create: `torsearch/search/filters.py`
- Test: `tests/test_filters.py`

- [ ] **Step 1: Write the failing test**

`tests/test_filters.py`:
```python
from datetime import datetime, timezone

from torsearch.models import Category, SearchResult
from torsearch.search.filters import ResultFilters, apply, detect_quality


def _r(title="X", size=1000, seeders=10, leechers=1, date=None):
    return SearchResult(
        title=title, size=size, seeders=seeders, leechers=leechers,
        source="t", category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:" + title.replace(" ", "_"),
        publish_date=date,
    )


def test_detect_quality():
    assert detect_quality("Movie.2024.2160p.x265") == "2160p"
    assert detect_quality("Movie.4K.HDR") == "2160p"
    assert detect_quality("Movie.1080p.BluRay") == "1080p"
    assert detect_quality("Show.S01.720p") == "720p"
    assert detect_quality("Old.480p.DVD") == "480p"
    assert detect_quality("Some.Release.Group") == "other"


def test_filter_min_seeders():
    out = apply([_r("A", seeders=5), _r("B", seeders=50)], ResultFilters(min_seeders=10))
    assert [r.title for r in out] == ["B"]


def test_filter_size_range():
    gb = 1024 ** 3
    out = apply([_r("small", size=gb), _r("big", size=10 * gb)], ResultFilters(min_size=2 * gb, max_size=20 * gb))
    assert [r.title for r in out] == ["big"]


def test_filter_quality_subset():
    out = apply([_r("Movie.1080p"), _r("Movie.720p")], ResultFilters(qualities=["1080p"]))
    assert [r.title for r in out] == ["Movie.1080p"]


def test_filter_quality_empty_keeps_all():
    assert len(apply([_r("Movie.1080p"), _r("Movie.720p")], ResultFilters(qualities=[]))) == 2


def test_filter_exclude_case_insensitive():
    out = apply([_r("Movie.CAM.xvid"), _r("Movie.1080p")], ResultFilters(exclude=["cam"]))
    assert [r.title for r in out] == ["Movie.1080p"]


def test_sort_size_asc():
    res = [_r("big", size=300), _r("small", size=100), _r("mid", size=200)]
    out = apply(res, ResultFilters(sort="size", direction="asc"))
    assert [r.title for r in out] == ["small", "mid", "big"]


def test_sort_seeders_desc_is_default():
    res = [_r("a", seeders=1), _r("b", seeders=9), _r("c", seeders=5)]
    assert [r.title for r in apply(res, ResultFilters())] == ["b", "c", "a"]


def test_sort_title_asc_case_insensitive():
    res = [_r("Zeta"), _r("alpha"), _r("Mango")]
    out = apply(res, ResultFilters(sort="title", direction="asc"))
    assert [r.title for r in out] == ["alpha", "Mango", "Zeta"]


def test_sort_date_desc_handles_missing_dates():
    d_old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    d_new = datetime(2024, 1, 1, tzinfo=timezone.utc)
    res = [_r("old", date=d_old), _r("new", date=d_new), _r("undated", date=None)]
    out = apply(res, ResultFilters(sort="date", direction="desc"))
    assert [r.title for r in out][:2] == ["new", "old"]


def test_invalid_sort_and_direction_fall_back():
    res = [_r("a", seeders=1), _r("b", seeders=9)]
    out = apply(res, ResultFilters(sort="bogus", direction="weird"))
    assert [r.title for r in out] == ["b", "a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'torsearch.search.filters'`.

- [ ] **Step 3: Write minimal implementation**

`torsearch/search/filters.py`:
```python
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from torsearch.models import SearchResult

_QUALITY_PATTERNS = [
    ("2160p", re.compile(r"\b(2160p|4k|uhd)\b", re.IGNORECASE)),
    ("1080p", re.compile(r"\b1080p\b", re.IGNORECASE)),
    ("720p", re.compile(r"\b720p\b", re.IGNORECASE)),
    ("480p", re.compile(r"\b(480p|sd)\b", re.IGNORECASE)),
]

VALID_SORTS = {"title", "size", "seeders", "leechers", "date"}
VALID_DIRECTIONS = {"asc", "desc"}


def detect_quality(title: str) -> str:
    for label, pattern in _QUALITY_PATTERNS:
        if pattern.search(title):
            return label
    return "other"


class ResultFilters(BaseModel):
    min_seeders: int = 0
    min_size: int | None = None
    max_size: int | None = None
    qualities: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    sort: str = "seeders"
    direction: str = "desc"


_SORT_KEYS = {
    "title": lambda r: r.title.lower(),
    "size": lambda r: r.size,
    "seeders": lambda r: r.seeders,
    "leechers": lambda r: r.leechers,
    "date": lambda r: r.publish_date.timestamp() if r.publish_date else 0.0,
}


def apply(results: list[SearchResult], filters: ResultFilters) -> list[SearchResult]:
    excluded = [w.lower() for w in filters.exclude if w]
    kept: list[SearchResult] = []
    for r in results:
        if r.seeders < filters.min_seeders:
            continue
        if filters.min_size is not None and r.size < filters.min_size:
            continue
        if filters.max_size is not None and r.size > filters.max_size:
            continue
        if filters.qualities and detect_quality(r.title) not in filters.qualities:
            continue
        title_lower = r.title.lower()
        if any(word in title_lower for word in excluded):
            continue
        kept.append(r)

    sort = filters.sort if filters.sort in VALID_SORTS else "seeders"
    direction = filters.direction if filters.direction in VALID_DIRECTIONS else "desc"
    kept.sort(key=_SORT_KEYS[sort], reverse=(direction == "desc"))
    return kept
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_filters.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add torsearch/search/filters.py tests/test_filters.py
git commit -m "feat: add result filtering and sorting module"
```

---

## Task 2: Brancher filtres + tri sur la recherche

**Files:**
- Modify: `torsearch/web/routes.py`
- Modify: `torsearch/web/templates/index.html`
- Modify: `torsearch/web/templates/partials/results.html`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests (append to `tests/test_web.py`)**

Append to `tests/test_web.py`:
```python
def _result(title, size=1000, seeders=10, leechers=1):
    return SearchResult(
        title=title, size=size, seeders=seeders, leechers=leechers,
        source="t1", category=Category.MOVIES,
        download_url="magnet:?xt=urn:btih:" + title.replace(" ", "_"),
    )


def test_search_applies_min_seeders_filter():
    client, _ = _make([_result("LowSeed", seeders=2), _result("HighSeed", seeders=80)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "10"})
    assert resp.status_code == 200
    assert "HighSeed" in resp.text
    assert "LowSeed" not in resp.text


def test_search_quality_filter():
    client, _ = _make([_result("Film 1080p BluRay"), _result("Film 720p WEB")])
    resp = client.get("/search", params={"q": "x", "quality": "1080p"})
    assert "1080p BluRay" in resp.text
    assert "720p WEB" not in resp.text


def test_search_exclude_word():
    client, _ = _make([_result("Film CAM"), _result("Film Clean 1080p")])
    resp = client.get("/search", params={"q": "x", "exclude": "cam"})
    assert "Film Clean 1080p" in resp.text
    assert "Film CAM" not in resp.text


def test_search_sort_size_ascending():
    client, _ = _make([_result("BigOne", size=3_000_000_000), _result("SmallOne", size=1_000_000_000)])
    resp = client.get("/search", params={"q": "x", "sort": "size", "dir": "asc"})
    assert resp.text.index("SmallOne") < resp.text.index("BigOne")


def test_search_invalid_filter_params_do_not_500():
    client, _ = _make([_result("KeepMe", seeders=5)])
    resp = client.get("/search", params={"q": "x", "min_seeders": "abc", "min_size_gb": "xyz"})
    assert resp.status_code == 200
    assert "KeepMe" in resp.text


def test_search_renders_sortable_headers():
    client, _ = _make([_result("Anything")])
    resp = client.get("/search", params={"q": "x"})
    assert "hx-vals" in resp.text
    assert "Seed" in resp.text
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: FAIL — filters are not applied yet (e.g. `LowSeed` still present) and `hx-vals` not in the template.

- [ ] **Step 3: Update the `/search` route**

In `torsearch/web/routes.py`, update the imports at the top to:
```python
from __future__ import annotations

import re

from fastapi import APIRouter, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse

from torsearch.context import AppContext
from torsearch.models import Category
from torsearch.search.filters import VALID_DIRECTIONS, VALID_SORTS, ResultFilters, apply
from torsearch.web.settings_routes import settings_router
from torsearch.web.templating import templates
```
(Keep whatever other imports already exist; the key additions are `re`, `Query`, and the `filters` import.)

Add these two helpers just below `router = APIRouter()`:
```python
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
```

Replace the existing `search` handler with:
```python
@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    cat: str = "all",
    min_seeders: str = "0",
    min_size_gb: str = "",
    max_size_gb: str = "",
    quality: list[str] = Query(default=[]),
    exclude: str = "",
    sort: str = "seeders",
    dir: str = "desc",
):
    ctx: AppContext = request.app.state.ctx
    try:
        category = Category(cat)
    except ValueError:
        category = Category.ALL
    raw = await ctx.search_service.search(q, category) if q.strip() else []

    effective_sort = sort if sort in VALID_SORTS else "seeders"
    effective_dir = dir if dir in VALID_DIRECTIONS else "desc"
    filters = ResultFilters(
        min_seeders=max(_to_int(min_seeders), 0),
        min_size=_to_size_bytes(min_size_gb),
        max_size=_to_size_bytes(max_size_gb),
        qualities=[item for item in quality if item],
        exclude=[w for w in re.split(r"[\s,]+", exclude) if w],
        sort=effective_sort,
        direction=effective_dir,
    )
    results = apply(raw, filters)
    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {"results": results, "query": q, "sort": effective_sort, "dir": effective_dir},
    )
```

- [ ] **Step 4: Add the filters panel to `index.html`**

Replace the entire contents of `torsearch/web/templates/index.html` with:
```html
{% extends "base.html" %}
{% block content %}
<form id="search-form" hx-get="/search" hx-target="#results" hx-indicator="#spinner" class="mb-6">
  <div class="flex flex-wrap gap-3">
    <input type="text" name="q" placeholder="Rechercher un film, une serie..." autofocus
           class="flex-1 min-w-[240px] rounded bg-slate-800 border border-slate-700 px-4 py-2">
    <select name="cat" class="rounded bg-slate-800 border border-slate-700 px-3 py-2">
      {% for c in categories %}
      <option value="{{ c.value }}">{{ c.value | capitalize }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="rounded bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold px-5 py-2">Chercher</button>
    <span id="spinner" class="htmx-indicator self-center text-slate-400">Recherche...</span>
  </div>
  <details class="mt-3 text-sm">
    <summary class="cursor-pointer text-slate-400 hover:text-slate-200">Filtres</summary>
    <div class="mt-3 flex flex-wrap items-end gap-4">
      <label class="text-xs text-slate-400">Seeders min<br>
        <input type="number" name="min_seeders" value="0" min="0" class="w-24 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille min (Go)<br>
        <input type="number" name="min_size_gb" step="0.1" min="0" class="w-24 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <label class="text-xs text-slate-400">Taille max (Go)<br>
        <input type="number" name="max_size_gb" step="0.1" min="0" class="w-24 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
      <fieldset class="text-xs text-slate-400">
        <legend>Qualite</legend>
        <div class="flex gap-2">
          {% for qv in ["2160p", "1080p", "720p", "480p", "other"] %}
          <label class="flex items-center gap-1"><input type="checkbox" name="quality" value="{{ qv }}"> {{ qv }}</label>
          {% endfor %}
        </div>
      </fieldset>
      <label class="text-xs text-slate-400">Exclure ces mots<br>
        <input type="text" name="exclude" placeholder="cam, ts, multi" class="w-48 rounded bg-slate-800 border border-slate-700 px-2 py-1"></label>
    </div>
  </details>
</form>
<div id="results"></div>
{% endblock %}
```

- [ ] **Step 5: Add sortable headers + Date column to `results.html`**

Replace the entire contents of `torsearch/web/templates/partials/results.html` with:
```html
{% macro sorth(col, label, extra='') %}
  {%- set next_dir = 'desc' if (sort == col and dir == 'asc') else 'asc' -%}
  <th class="{{ extra }} cursor-pointer select-none hover:text-slate-200"
      hx-get="/search" hx-include="#search-form" hx-target="#results"
      hx-vals='{"sort": "{{ col }}", "dir": "{{ next_dir }}"}'>
    {{ label }}{% if sort == col %}{{ ' ▲' if dir == 'asc' else ' ▼' }}{% endif %}
  </th>
{% endmacro %}
{% if not results %}
  <p class="text-slate-400">Aucun resultat{% if query %} pour "{{ query }}"{% endif %}.</p>
{% else %}
<table class="w-full text-sm">
  <thead class="text-left text-slate-400 border-b border-slate-700">
    <tr>
      {{ sorth('title', 'Nom') }}
      <th>Source</th>
      {{ sorth('size', 'Taille', 'text-right') }}
      {{ sorth('seeders', 'Seed', 'text-right') }}
      {{ sorth('leechers', 'Leech', 'text-right') }}
      {{ sorth('date', 'Date', 'text-right') }}
      <th></th>
    </tr>
  </thead>
  <tbody>
  {% for r in results %}
    <tr class="border-b border-slate-800 hover:bg-slate-800/50">
      <td class="py-2 pr-3">{{ r.title }}</td>
      <td><span class="rounded bg-slate-700 px-2 py-0.5 text-xs">{{ r.source }}</span></td>
      <td class="text-right whitespace-nowrap">{{ (r.size / 1073741824) | round(2) }} Go</td>
      <td class="text-right text-emerald-400">{{ r.seeders }}</td>
      <td class="text-right text-slate-400">{{ r.leechers }}</td>
      <td class="text-right text-slate-400 whitespace-nowrap">{{ r.publish_date.strftime('%Y-%m-%d') if r.publish_date else '-' }}</td>
      <td class="text-right whitespace-nowrap">
        <form hx-post="/download" hx-target="#toast" class="inline">
          <input type="hidden" name="download_url" value="{{ r.download_url }}">
          <button class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-xs">+ Transmission</button>
        </form>
        <button class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs"
                onclick="navigator.clipboard.writeText('{{ r.download_url }}')">Copier</button>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS — the 6 new web tests green, and all pre-existing tests (the previous `/search` rendering tests still pass: titles + seeders still render, empty query still shows the placeholder).

- [ ] **Step 7: Commit**

```bash
git add torsearch/web/routes.py torsearch/web/templates/index.html torsearch/web/templates/partials/results.html tests/test_web.py
git commit -m "feat: wire result filters and column sorting into search UI"
```

---

## Notes de vérification finale (manuel, hors TDD)

1. Lancer `uvicorn torsearch.main:get_app --factory --reload`, faire une recherche, déplier
   **Filtres**, régler « Seeders min » / cocher une qualité / saisir un mot à exclure → relancer
   et vérifier que la liste se réduit.
2. Cliquer sur les en-têtes **Taille / Seed / Date** → l'ordre change et l'indicateur ▲/▼
   apparaît sur la colonne active ; recliquer inverse le sens.
