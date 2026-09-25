# Plan d'implémentation : Section Séries Découvrir & Bouton Torrents vers Recherche

Date : 2026-09-25

## Tâche 1 : TMDB Client - Trending movies & tv (TDD)
- [ ] Écrire les tests dans `tests/test_tmdb.py` pour `trending("movie")` et `trending("tv")`.
- [ ] Mettre à jour `parse_multi` et `trending` dans `torsearch/metadata/tmdb.py`.
- [ ] Exécuter `pytest tests/test_tmdb.py`.

## Tâche 2 : Page Recherche `/?q=...&cat=...` avec auto-recherche (TDD)
- [ ] Écrire le test dans `tests/test_web.py` pour `GET /?q=...&cat=...`.
- [ ] Mettre à jour `index` dans `torsearch/web/routes.py` et `index.html`.
- [ ] Exécuter `pytest tests/test_web.py`.

## Tâche 3 : Route Découvrir & Templates avec sections Films/Séries et lien Torrents (TDD)
- [ ] Écrire les tests dans `tests/test_discover_web.py`.
- [ ] Mettre à jour `torsearch/web/discover_routes.py`.
- [ ] Mettre à jour `torsearch/web/templates/discover.html` et `torsearch/web/templates/partials/media_results.html`.
- [ ] Vérifier les tests avec `pytest -q`, `tests/test_no_inline_js.py`, `ruff`, et `mypy`.

## Tâche 4 : Commit, push et release Docker
- [ ] Bump de version si nécessaire ou commit.
- [ ] Validation globale (484+ tests).
