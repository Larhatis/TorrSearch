# Chantier 2 : Moteur de décision & auto-grab intelligent — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'auto-grab des films et séries robuste et intelligent : éliminer les faux positifs de titre (« Lost in Space » pour « Lost »), chercher avec le titre original TMDB, analyser précisément les releases (langue MULTI/VFF/VOSTFR, source, codec), bannir automatiquement les releases dégradées (CAM/TS), blacklister les torrents en échec et trier selon les préférences utilisateur.

**Architecture :**
- `torsearch/parser/release.py` : analyse syntaxique du nom de release (résolution, source, codec, langue, épisodes, titre nettoyé).
- `torsearch/search/matcher.py` : comparaison stricte de titres (français et original, avec gestion d'année).
- `torsearch/search/decision.py` : moteur de sélection et de classement (élimination des sources bannies, langues préférées MULTI/VFF > VF > VOSTFR, départage par seeders/taille).
- `torsearch/library/blacklist.py` : collection SQLite pour blacklister les torrents défaillants ou morts.
- `torsearch/models.py` & `torsearch/metadata/tmdb.py` : enrichissement avec `original_title`.
- `torsearch/monitor/runner.py` : branchement des cycles films et séries sur le nouveau moteur de décision avec recherche multi-titres et gestion de la liste noire.

**Tech Stack :** Python 3.12+, FastAPI, SQLite, Pydantic, pytest (+ pytest-asyncio, respx).

**Commandes de validation :** `.venv/bin/pytest`, `.venv/bin/ruff check torsearch tests`, `.venv/bin/mypy`.

---

## Structure des fichiers

- **Créer** `torsearch/parser/__init__.py`
- **Créer** `torsearch/parser/release.py`
- **Créer** `torsearch/search/matcher.py`
- **Créer** `torsearch/search/decision.py`
- **Créer** `torsearch/library/blacklist.py`
- **Modifier** `torsearch/models.py` — `original_title` sur `MediaResult`, `WantedMovie`, `WantedSeries`.
- **Modifier** `torsearch/metadata/tmdb.py` — capture de `original_title` / `original_name`.
- **Modifier** `torsearch/library/movies.py` & `series.py` — stockage et support de `original_title`.
- **Modifier** `torsearch/monitor/runner.py` — intégration du moteur de décision, double recherche et blacklist.
- **Tests** :
  - `tests/test_release_parser.py` (nouveau)
  - `tests/test_matcher.py` (nouveau)
  - `tests/test_decision.py` (nouveau)
  - `tests/test_blacklist.py` (nouveau)
  - `tests/test_monitor_cycle_decision.py` (nouveau)
  - Ajustement des tests existants impactés (`test_tmdb.py`, `test_monitor_runner.py`).

---

## Task 1 : Analyseur de nom de release (`torsearch/parser/release.py`)

**Files:** `torsearch/parser/__init__.py`, `torsearch/parser/release.py`, `tests/test_release_parser.py`

- [ ] **Step 1 : Tests unitaires** (`tests/test_release_parser.py`) :
  - Détection des langues : `MULTI`, `TRUEFRENCH`/`VFF`, `VFQ`, `FRENCH`/`VF`, `VOSTFR`/`SUBFRENCH`, `VO`.
  - Détection des sources et sources bannies : `CAM`, `TS`, `TELESYNC`, `TC`, `SCR`, `DVDSCR` (`is_banned_source=True`) vs `BluRay`, `WEB-DL`, `WEBRip`, `HDTV` (`is_banned_source=False`).
  - Détection des résolutions (`2160p`, `1080p`, `720p`, `480p`, `unknown`).
  - Détection des codecs (`x264`, `x265`, `hevc`, `av1`).
  - Extraction de l'année et des épisodes (`SxxEyy`).
  - Extraction du titre propre sans les métadonnées.

- [ ] **Step 2 : Exécuter pytest** → FAIL (fichier introuvable).
- [ ] **Step 3 : Implémenter `torsearch/parser/release.py`** et `torsearch/parser/__init__.py`.
- [ ] **Step 4 : Vérifier** → `.venv/bin/pytest tests/test_release_parser.py -q` passe à 100%.

---

## Task 2 : Vérification stricte de correspondance de titre (`torsearch/search/matcher.py`)

**Files:** `torsearch/search/matcher.py`, `tests/test_matcher.py`

- [ ] **Step 1 : Tests unitaires** (`tests/test_matcher.py`) :
  - Rejet des faux positifs : `Lost.in.Space.S01E01` rejeté pour la série `Lost`.
  - Rejet des suites : `Avatar.The.Way.of.Water.2022` rejeté pour `Avatar (2009)`.
  - Acceptation des correspondances exactes nettoyées (accents, tirets, points, ponctuation, casse) pour `Lost.S01E01.FRENCH...`.
  - Support de la correspondance sur `original_title` (ex: release `Breaking.Bad.S01E01...` correspond pour `Le Trône de Fer` / `Game of Thrones`).
  - Vérification de l'année pour les films avec tolérance de 1 an.

- [ ] **Step 2 : Exécuter pytest** → FAIL.
- [ ] **Step 3 : Implémenter `torsearch/search/matcher.py`**.
- [ ] **Step 4 : Vérifier** → `.venv/bin/pytest tests/test_matcher.py -q` passe à 100%.

---

## Task 3 : Moteur de décision & classement (`torsearch/search/decision.py`)

**Files:** `torsearch/search/decision.py`, `tests/test_decision.py`

- [ ] **Step 1 : Tests unitaires** (`tests/test_decision.py`) :
  - Rejet des sources bannies (`CAM`, `TS`, `TC`, etc.).
  - Rejet des titres non correspondants.
  - Rejet des résolutions non désirées.
  - Rejet de la VO pure sans sous-titres français.
  - Hiérarchisation :
    - MULTI et VFF (Rang 1) > VF (Rang 2) > VOSTFR (Rang 3).
    - À langue égale, respect de l'ordre de résolution.
    - À langue et résolution égales, départage par seeders (ou plus petit fichier couvrant pour les packs séries).

- [ ] **Step 2 : Exécuter pytest** → FAIL.
- [ ] **Step 3 : Implémenter `torsearch/search/decision.py`**.
- [ ] **Step 4 : Vérifier** → `.venv/bin/pytest tests/test_decision.py -q` passe à 100%.

---

## Task 4 : Liste noire persistante (`torsearch/library/blacklist.py`)

**Files:** `torsearch/library/blacklist.py`, `tests/test_blacklist.py`

- [ ] **Step 1 : Tests unitaires** (`tests/test_blacklist.py`) :
  - Ajout d'une release en liste noire avec raison (`failed`, `dead`, `manual`).
  - Vérification `is_blacklisted(infohash, title)`.
  - Suppression d'un élément de la liste noire.
  - Persistance dans SQLite via `as_collection(source, "blacklist")`.

- [ ] **Step 2 : Exécuter pytest** → FAIL.
- [ ] **Step 3 : Implémenter `torsearch/library/blacklist.py`**.
- [ ] **Step 4 : Vérifier** → `.venv/bin/pytest tests/test_blacklist.py -q` passe à 100%.

---

## Task 5 : Support du Titre Original dans TMDB & Modèles

**Files:** `torsearch/models.py`, `torsearch/metadata/tmdb.py`, `torsearch/library/movies.py`, `torsearch/library/series.py`, `tests/test_tmdb.py`

- [ ] **Step 1 : Tests** sur l'extraction d'`original_title` / `original_name` dans `tests/test_tmdb.py` et la persistance dans `tests/test_library.py`.
- [ ] **Step 2 : Exécuter pytest** → FAIL.
- [ ] **Step 3 : Modifier** `torsearch/models.py`, `torsearch/metadata/tmdb.py`, `torsearch/library/movies.py`, `torsearch/library/series.py`.
- [ ] **Step 4 : Vérifier** → `.venv/bin/pytest tests/test_tmdb.py -q` passe à 100%.

---

## Task 6 : Intégration dans le moniteur de surveillance (`torsearch/monitor/runner.py`)

**Files:** `torsearch/monitor/runner.py`, `torsearch/context.py`, `tests/test_monitor_cycle_decision.py`

- [ ] **Step 1 : Tests d'intégration** :
  - `run_movie_cycle` utilise le moteur de décision, cherche le titre + titre original, et blackliste le précédent grab en cas d'échec constaté (re-grab).
  - `run_series_cycle` utilise le moteur de décision et rejette les faux positifs de titre tout en choisissant le torrent le plus adapté pour combler les épisodes manquants.
- [ ] **Step 2 : Exécuter pytest** → FAIL.
- [ ] **Step 3 : Implémenter** les modifications dans `torsearch/monitor/runner.py` et injecter la `Blacklist` dans `AppContext`.
- [ ] **Step 4 : Vérifier** → suite complète `.venv/bin/pytest`, `.venv/bin/ruff check torsearch tests`, `.venv/bin/mypy` verte.
