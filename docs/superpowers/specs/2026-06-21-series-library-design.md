# Phase C — Bibliothèque Séries (Sonarr-lite) — Design

**Date :** 2026-06-21
**Statut :** validé

## Objectif

Troisième brique de l'étoile polaire (remplacer Sonarr). Suivre des **séries** ajoutées depuis la
découverte TMDB : le monitor cherche la série en boucle, **parse les identifiants d'épisode**
(`SxxEyy`) des torrents et **auto-grabbe chaque nouvel épisode** (et les packs de saison) pas encore
obtenu, en mémorisant les épisodes obtenus. Suivi **par épisode** — attrape les séries en cours.

Parallèle direct de la Phase B (films), avec une difficulté propre : le parsing TV et le grab
**multiple par cycle**.

Non-objectifs (Phase C) : grille épisode-par-épisode dans l'UI (juste un compteur), sélection de
saisons à suivre (on suit toute la série), métadonnées d'épisodes TMDB (nombre d'épisodes/dates),
séries quotidiennes (`YYYY.MM.DD`), upgrade de qualité.

## Décisions (validées)

- Suivi **par épisode** (parser `SxxEyy`).
- **Profil de qualité partagé** films/séries : on réutilise `LibraryConfig` (`config.library`).
- On suit **toute la série** (toutes saisons).
- **Pas de grille épisodes** en v1 : la carte série affiche juste « N épisodes obtenus ».
- Clés épisode/saison **indépendantes** : un pack de saison (`S02`) est une clé distincte d'un
  épisode (`S02E05`). Conséquence assumée : si on a déjà des épisodes puis qu'un pack de saison
  apparaît, le pack est (re)grabbé. Simplification v1.
- La page **Bibliothèque** affiche **deux sections (Films & Séries)** — pas de nouvelle entrée nav.

## Le parser TV — `torsearch/library/episodes.py` (créé)

`parse_episodes(title: str) -> set[str]` (fonction pure, insensible à la casse) :
- Épisode(s) : motif `S(\d{1,2})` suivi d'une série de `E(\d{1,2})` → clés `f"S{ss:02d}E{ee:02d}"`.
  - `S02E05` → `{"S02E05"}` ; `S02E05E06` / `S02E05-E06` → `{"S02E05","S02E06"}`.
  - Zéro-padding : `S1E5` → `{"S01E05"}`.
- Pack de saison (si **aucun** `SxxEyy`) : `S(\d{1,2})` seul, `Season (\d+)`, `Saison (\d+)`,
  ou présence de `complete` avec un numéro de saison → clé `f"S{ss:02d}"`.
- Rien d'identifiable → `set()` (le cycle ne grabbe pas ce résultat).

## Composants & fichiers

### 1. Modèle — `torsearch/models.py` (modifié)

`WantedSeries(BaseModel)` :
- `tmdb_id: int`, `title: str`, `year: str | None = None`, `poster_path: str | None = None`,
  `added_at: datetime`, `grabbed: list[str] = []` (clés obtenues).
- `@computed_field poster_url` (même logique que `WantedMovie`/`MediaResult`).

### 2. Store — `torsearch/library/series.py` (créé)

`SeriesLibrary` (calqué sur `MovieLibrary`, JSON atomique, `data/series.json`) :
- `list() -> list[WantedSeries]`, `add(series) -> bool` (dédup `tmdb_id`),
  `remove(tmdb_id) -> None`,
  `mark_grabbed(tmdb_id, keys: list[str]) -> None` (union des clés dans `grabbed`).

### 3. Cycle — `torsearch/monitor/runner.py` (modifié)

`run_series_cycle(config, series_library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]` :
- si `not config.monitor.enabled` ou `series_library is None` → `[]`.
- pour chaque `series` de `series_library.list()` :
  - `results = await search_service.search(series.title, Category.TV)` (résilient).
  - `kept = apply(results, ResultFilters(min_seeders=config.library.min_seeders, qualities=config.library.qualities, sort="seeders", direction="desc"))`.
  - `have = set(series.grabbed)` ; `newly = []`.
  - pour chaque résultat de `kept` : `keys = parse_episodes(r.title)` ; si `keys - have` non vide →
    `transmission.add(r.download_url)` (try/continue), `have |= keys`, `newly += keys`,
    `MonitorRecord(search=series.title, title=r.title, kind="grabbed", ...)` → `history.add` + notif.
  - si `newly` : `series_library.mark_grabbed(series.tmdb_id, sorted(set(newly)))`.
- **Grabbe plusieurs épisodes par cycle** ; dédup intra-cycle via `have`.

`MonitorRunner.__init__` reçoit `series_library` ; `_loop` appelle `run_cycle`, puis
`run_movie_cycle`, puis `run_series_cycle`.

### 4. Câblage — `torsearch/main.py` + `torsearch/web/routes.py` (modifiés)

`build_app` crée `series_library = SeriesLibrary(series_path)` (`data/series.json`, env
`TORSEARCH_SERIES`), le passe à `create_app(..., series_library=...)` (→ `app.state.series_library`)
et à `MonitorRunner(..., series_library=series_library)`. Mirroir de `library`.

### 5. Web — `torsearch/web/series_routes.py` (créé) + templates

- `POST /series/add` (form `tmdb_id`, `title`, `year`, `poster_path`) →
  `series_library.add(WantedSeries(...))` → `partials/toast.html`.
- `POST /series/{tmdb_id}/remove` → `series_library.remove` → re-rend `partials/series_list.html`.
- Page **Bibliothèque** (`library.html`) : devient **deux sections** — « Films »
  (`partials/library_list.html`, existant) et « Séries » (`partials/series_list.html`, nouveau).
  `library_page` lit `app.state.library` **et** `app.state.series_library`.
- `partials/series_list.html` : grille d'affiches, titre, **« N épisodes obtenus »**
  (`series.grabbed | length`), bouton Retirer (`POST /series/{tmdb_id}/remove`, cible `#series-list`).
- `partials/media_results.html` (Découvrir) : carte **série** (`media_type == 'tv'`) → bouton
  **« Suivre »** (`POST /series/add`, `hx-vals` en guillemets simples + `tojson`).

## Flux de données

1. Découvrir (carte série) → « Suivre » → `POST /series/add` → `data/series.json`.
2. `MonitorRunner._loop` (si surveillance ON) → `run_series_cycle` → recherche + filtres profil →
   parse épisodes → grab des nouveaux → `mark_grabbed` (union des clés) → historique + notif.
3. `GET /library` → sections Films & Séries reflètent l'état.

## Gestion des erreurs / cas limites

- Surveillance OFF → aucun cycle séries.
- Résultat sans identifiant d'épisode parsable → ignoré (pas de grab).
- Erreur réseau/tracker/Transmission sur une série → loggée, on continue.
- Ajout d'une série déjà présente → ignoré (dédup `tmdb_id`).
- `data/series.json` absent → bibliothèque séries vide.

## Tests

- `tests/test_episode_parser.py` : `parse_episodes` — `S01E01`, multi `S02E05E06` / `S02E05-E06`,
  zéro-pad `S1E5`, pack `S02`/`Season 3`/`Saison 1`/`...Complete...`, non parsable → `set()`,
  insensibilité à la casse.
- `tests/test_series_library.py` : `add`/dédup, `remove`, `mark_grabbed` (union, persistance JSON).
- `tests/test_models.py` (ajout) : `WantedSeries.poster_url`.
- `tests/test_monitor_runner.py` (ajouts) : `run_series_cycle` grabbe les épisodes nouveaux
  (plusieurs en un cycle), dédup intra-cycle (2 releases du même épisode → 1 grab), ignore les
  déjà-obtenus, gating monitor off, respecte le profil qualité, résilience erreur.
- `tests/test_series_web.py` : `POST /series/add` ajoute ; `GET /library` montre la section Séries
  + compteur d'épisodes ; `POST /series/{id}/remove` retire ; carte série de Découvrir a le bouton
  « Suivre ».
- Non-régression : suite existante (204) reste verte.
