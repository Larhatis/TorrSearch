# Plan : Gestion détaillée des séries par saison et épisode (Style Sonarr)

Date : 2026-09-26

## 1. Modèles de données
- Ajouter `EpisodeInfo` et `SeasonInfo` dans `torsearch/models.py`.
- Tester la sérialisation / désérialisation et computed fields (`season_tag`, `poster_url`).

## 2. Bibliothèque Séries
- Ajouter `get(self, tmdb_id: int) -> WantedSeries | None` dans `torsearch/library/series.py`.
- Écrire le test unitaire correspondant dans `tests/test_series_library.py`.

## 3. Client TMDB
- Ajouter `seasons(tv_id: int) -> list[SeasonInfo]` dans `torsearch/metadata/tmdb.py`.
- Rendre les requêtes de saisons parallèles (`asyncio.gather`).
- Faire appel à `seasons(tv_id)` dans `episodes(tv_id)`.
- Écrire les tests unitaires dans `tests/test_tmdb.py` :
  - Parsing complet des saisons et épisodes.
  - Gestion du cache.
  - Résilience aux erreurs réseau.

## 4. Routes Web et Intégration
- Ajouter `GET /series/{tmdb_id}` et `GET /series/{tmdb_id}/detail` dans `torsearch/web/series_routes.py`.
- Récupérer les épisodes Jellyfin si la série est présente.
- Construire le modèle de vue pour chaque saison (compteurs d'acquisition, badges, liens de recherche).
- Écrire les tests d'intégration dans `tests/test_series_web.py`.

## 5. Templates HTML
- Créer `torsearch/web/templates/partials/series_detail_modal.html`.
- Créer `torsearch/web/templates/series_detail.html` (page complète si accès direct).
- Mettre à jour `torsearch/web/templates/partials/series_list.html` avec le bouton « Saisons & Episodes » et l'affiche cliquable.
- Mettre à jour `torsearch/web/templates/partials/media_detail_modal.html` avec un lien direct vers la vue saisons/épisodes pour les séries.

## 6. Vérifications et Release
- Exécuter les tests : `pytest -q`.
- Vérifier l'absence de JS inline : `pytest tests/test_no_inline_js.py`.
- Linter et typage : `ruff check torsearch tests` et `mypy`.
- Mettre à jour la version dans `pyproject.toml` (0.3.6) et `AGENTS.md`.
- Commit, tag `v0.3.6`, push sur `origin main` et `origin v0.3.6`.
