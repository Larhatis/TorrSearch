# Améliorations Découvrir : Section Séries & Navigation vers Recherche Torrents

Date : 2026-09-25

## 1. Objectifs

1. **Séparation Films / Séries dans Découvrir** :
   Afficher distinctement les **Films du moment** et les **Séries du moment** dans la page Découvrir (`/discover`), avec des onglets de filtrage rapide (Tous / Films / Séries).
2. **Fonctionnement du bouton Torrents** :
   Remplacer l'injection HTMX invisible en bas de page par un lien direct vers la page de recherche (`/?q=...&cat=...`), qui pré-remplit le champ de recherche, sélectionne la catégorie et lance automatiquement la recherche de torrents sur tous les trackers au chargement.

## 2. Conception technique

### 2.1 TMDB Client (`torsearch/metadata/tmdb.py`)
- Mettre à jour `parse_multi(payload, default_type=None)` pour supporter les payloads TMDB sans champ `media_type` explicite (comme `/trending/movie/week` et `/trending/tv/week`).
- Étendre `trending(media_type: str = "all")` pour accepter `media_type in ("all", "movie", "tv")`.
- Ajouter `trending_movies()` et `trending_series()`.

### 2.2 Routes Découvrir (`torsearch/web/discover_routes.py`)
- Route `GET /discover/trending` :
  - Paramètre optionnel `tab: str = "all"` (`"all"`, `"movie"`, `"tv"`).
  - Si `tab == "all"` : récupère en parallèle `movies` et `series` via `asyncio.gather`.
  - Si `tab == "movie"` : récupère uniquement les films tendances.
  - Si `tab == "tv"` : récupère uniquement les séries tendances.
  - Transmet `movies`, `series`, `tab` au template.

### 2.3 Page d'accueil / Recherche (`torsearch/web/routes.py` et `torsearch/web/templates/index.html`)
- Route `GET /` :
  - Accepte `q: str = ""` et `cat: str = "all"`.
  - Transmet `q` et `cat` à `index.html`.
- Template `index.html` :
  - Pré-remplit l'input `q` et le `<select name="cat">`.
  - Si `q` est renseigné : ajoute `hx-trigger="load"` au formulaire `#search-form` pour déclencher la recherche immédiatement dès l'arrivée sur la page.

### 2.4 Templates Découvrir (`torsearch/web/templates/discover.html` et `media_results.html`)
- Boutons d'onglets au-dessus des tendances : `Tous`, `Films`, `Series`.
- Affichage clair par sections :
  - Section **Films du moment** (icône `ti-movie`).
  - Section **Series du moment** (icône `ti-device-tv`).
- Bouton **Torrents** sur chaque carte :
  - Devient un lien `<a>` vers `/?q={{ (m.title ~ ' ' ~ (m.year or '')) | trim | urlencode }}&cat={{ 'movies' if m.media_type == 'movie' else 'tv' }}`.
  - Clique dessus &rarr; ouvre directement la page de recherche avec les résultats en cours de chargement.
- Respect strict de la règle zéro JS inline et conventions HTML sans accents.

## 3. Plan de tests (TDD)
1. `tests/test_tmdb.py` :
   - Tester `trending(media_type="movie")` et `trending(media_type="tv")`.
2. `tests/test_discover_web.py` :
   - Tester `/discover/trending` avec `tab=all`, `tab=movie`, `tab=tv`.
   - Vérifier que les sections Films et Séries sont présentes.
   - Vérifier que le bouton Torrents a le bon lien `/?q=...&cat=...`.
3. `tests/test_web.py` :
   - Tester que `GET /?q=Inception&cat=movies` pré-remplit le formulaire et contient `hx-trigger="load"`.
