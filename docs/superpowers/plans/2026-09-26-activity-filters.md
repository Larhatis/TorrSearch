# Plan de réalisation : Filtres par statut dans la vue Activité

Date : 2026-09-26

## Étape 1 : Tests unitaires (TDD)
- [ ] Ajouter des tests dans `tests/test_downloads_web.py` vérifiant :
  - Le filtrage par statut (`downloading`, `completed`, `active`, `paused`).
  - L'affichage des onglets avec compteurs.
  - La persistance du filtre dans les liens de rafraîchissement et actions.

## Étape 2 : Implémentation backend (`downloads_routes.py`)
- [ ] Ajouter `_filter_torrents(torrents, filter_status)` calculant les compteurs et filtrant la liste.
- [ ] Mettre à jour `_render_list` pour accepter `filter_status` et transmettre `filtered_torrents`, `counts`, `current_filter`.
- [ ] Mettre à jour `downloads_list`, `pause`, `resume`, `delete` pour accepter `filter: str = "all"`.

## Étape 3 : Implémentation template (`downloads_list.html`)
- [ ] Ajouter la barre d'onglets de filtrage avec compteurs.
- [ ] Adapter l'URL de rafraîchissement automatique : `/downloads/list?filter={{ current_filter }}`.
- [ ] Conserver `filter={{ current_filter }}` dans les requêtes POST d'action.

## Étape 4 : Validation Qualité & Déploiement
- [ ] Vérifier la suite de tests : `pytest -q`.
- [ ] Vérifier l'absence de JS inline : `pytest tests/test_no_inline_js.py -q`.
- [ ] Linter et typage : `ruff check torsearch tests` et `mypy`.
- [ ] Mettre à jour `pyproject.toml` (v0.3.5) et `AGENTS.md`.
- [ ] Commiter, taguer (`v0.3.5`) et pusher sur GitHub.
