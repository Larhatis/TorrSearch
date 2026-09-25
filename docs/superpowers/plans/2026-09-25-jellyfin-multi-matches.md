# Plan d'implémentation : Détection multi-titres Jellyfin sur Recherche

Date : 2026-09-25

## Tâche 1 : Méthode `find_matches` dans `JellyfinClient` (TDD)
- [ ] Écrire les tests dans `tests/test_jellyfin.py` :
  - `test_find_matches_returns_multiple_franchise_items()`
  - `test_find_matches_prioritizes_exact_over_partial()`
  - `test_find_matches_respects_limit()`
- [ ] Implémenter `find_matches` et brancher `find_matching` dessus dans `torsearch/jellyfin/client.py`.
- [ ] Exécuter les tests unitaires Jellyfin.

## Tâche 2 : Intégration Route Web & Template HTMX (TDD)
- [ ] Écrire le test dans `tests/test_web.py` :
  - `test_search_displays_multiple_jellyfin_matches_banner()`
- [ ] Mettre à jour `torsearch/web/routes.py` pour appeler `find_matches(q, limit=6)`.
- [ ] Mettre à jour `torsearch/web/templates/partials/results.html` pour supporter `jellyfin_matches`.
- [ ] Exécuter `pytest -q`, `ruff check torsearch tests`, `mypy`, et `tests/test_no_inline_js.py`.

## Tâche 3 : Commit, validation et push
- [ ] Vérifier tous les tests (478+).
- [ ] Commit `feat(jellyfin): display multiple matching items in search presence banner`.
- [ ] Push sur `origin/main`.
