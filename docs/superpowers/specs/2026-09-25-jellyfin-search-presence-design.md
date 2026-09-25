# Détection de présence Jellyfin sur la page de Recherche

Date : 2026-09-25

## 1. Objectif

Prévenir l'utilisateur lorsqu'il recherche un film ou une série sur la page de recherche manuelle (`/search`) s'il possède déjà ce titre sur son serveur Jellyfin, avec un lien direct pour le lire au lieu de lancer un téléchargement en double.

## 2. Conception technique

### 2.1 Modèle et Cache dans `JellyfinClient` (`torsearch/jellyfin/client.py`)
- Modèle `JellyfinItem(id: str, name: str, media_type: str, year: int | None, tmdb_id: str | None)`.
- Mise en cache en mémoire des éléments de la bibliothèque (`_items_cache`) avec une durée de vie (TTL) de 30 secondes pour garantir une recherche instantanée (< 1 ms).
- Réutilisation de l'appel `/Items` existant pour alimenter à la fois `owned()` (IDs TMDB) et `find_matching(query: str) -> JellyfinItem | None`.
- Matching par titre :
  1. Nettoyage du terme de recherche via `parse_release(query)` pour extraire le titre propre et l'année.
  2. Comparaison stricte avec `normalize_title` et `match_media_title` sur les noms et années des médias Jellyfin.
  3. Rejet garanti des faux positifs (Avatar 2 ne matche pas Avatar 1).

### 2.2 Route de recherche (`torsearch/web/routes.py`)
- Dans `GET /search` :
  - Si `ctx.jellyfin.enabled` et `q` non vide : `jellyfin_match = await ctx.jellyfin.find_matching(q)`.
  - Transmission au template `partials/results.html` de `jellyfin_match` et `jellyfin_url`.

### 2.3 Interface utilisateur (`torsearch/web/templates/partials/results.html`)
- En tête des résultats (que des torrents soient trouvés ou non) :
  - Bandeau vert distinct :
    - Icône de validation (`ti-circle-check`).
    - Texte : « Deja disponible sur votre Jellyfin : [Titre] ([Annee]) [Badge Film/Serie] ».
    - Bouton vert « ▶ Lire » ouvrant directement la page Jellyfin (`{jellyfin_url}/web/#/details?id={id}`).
- Respect des règles de sécurité : zéro JS inline, lien sécurisé avec `target="_blank" rel="noopener"`.

## 3. Plan de tests (TDD)
1. `tests/test_jellyfin.py` :
   - `test_get_items_parses_media_and_caches()` : vérifie l'extraction des films et séries avec nom, type, année et ID.
   - `test_find_matching_finds_exact_and_release_queries()` : teste la détection sur `"Inception"`, `"Inception 2010 1080p"`, `"Lost"`, et le rejet sur `"Avatar The Way of Water"` si seul Avatar 2009 est possédé.
2. `tests/test_web.py` :
   - `test_search_displays_jellyfin_banner_when_matched()` : vérifie que le bandeau avec le lien de lecture est rendu dans les résultats HTMX.
