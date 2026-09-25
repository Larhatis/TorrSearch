# Détection multi-titres Jellyfin sur la page de Recherche

Date : 2026-09-25

## 1. Objectif

Permettre d'afficher l'ensemble des films et séries d'une franchise ou d'une recherche générique (ex: « Batman », « Harry Potter ») déjà présents dans Jellyfin lors d'une recherche sur `/search`, au lieu de n'afficher qu'un seul élément au hasard.

## 2. Conception technique

### 2.1 Moteur de recherche Jellyfin (`torsearch/jellyfin/client.py`)
- Remplacement / extension avec `find_matches(query: str, limit: int = 6) -> list[JellyfinItem]` :
  1. Extraction du titre cible et de l'année avec `parse_release(query)`.
  2. Normalisation du titre (`normalize_title`).
  3. Recherche par étapes avec pondération :
     - **Tier 1 (Correspondance exacte)** : `normalize_title(item.name) == target_norm`.
     - **Tier 2 (Correspondance release / média)** : `match_media_title(parsed, item.name, item.year, is_series)`.
     - **Tier 3 (Correspondance par mots-clés / franchise)** : tous les mots significatifs de la recherche (longueur >= 2) sont contenus dans le titre Jellyfin normalisé ou son titre original.
  4. Classement :
     - Priorité Tier 1 > Tier 2 > Tier 3.
     - Bonus si l'année demandée correspond à l'année Jellyfin.
     - Tri secondaire par année décroissante (les plus récents en premier).
     - Dédoublonnage par `item.id` et limitation à `limit` (défaut 6).
- Rétrocompatibilité : `find_matching(query: str) -> JellyfinItem | None` appelle `find_matches(query, limit=1)` et renvoie le premier élément ou `None`.

### 2.2 Route Web (`torsearch/web/routes.py`)
- Appel de `find_matches(q, limit=6)` si Jellyfin est activé.
- Transmission de `jellyfin_matches` au template (et `jellyfin_match = matches[0]` pour repli).

### 2.3 Template UI (`torsearch/web/templates/partials/results.html`)
- Si 1 seul résultat : affichage du bandeau compact simple existant (« Deja disponible sur votre Jellyfin : ... »).
- Si > 1 résultats : bandeau multi-titres (« Deja disponibles sur votre Jellyfin (N) : ») listant chaque élément avec son nom, année, badge Film/Série et bouton « ▶ Lire » individuel.
- Zéro JS inline, convention sans accents dans le HTML.

## 3. Plan de tests (TDD)
1. `tests/test_jellyfin.py` :
   - Tester `find_matches` avec plusieurs titres correspondants (ex: « Batman » retourne Batman 1989, Batman Begins 2005, The Batman 2022).
   - Tester le respect de la limite.
   - Tester qu'une recherche précise (« Inception ») ne retourne que l'élément exact.
2. `tests/test_web.py` :
   - Tester que la recherche avec plusieurs correspondances Jellyfin rend le bandeau multi-titres avec chaque lien de lecture.
   - Tester que la recherche avec 1 seule correspondance conserve le bandeau unitaire.
