# Plan de réalisation : Suivi des téléchargements (Activité) et Actions Découvrir

Date : 2026-09-25

## Étape 1 : Transmission Client & Enrichissement de TorrentInfo
- [ ] Écrire un test unitaire dans `tests/test_transmission.py` ou `tests/test_transmission_client.py` vérifiant les champs et propriétés formatées de `TorrentInfo` (`size_formatted`, `down_rate_formatted`, `up_rate_formatted`, `eta_formatted`, `status_label`).
- [ ] Mettre à jour `TorrentInfo` et `TransmissionClient` dans `torsearch/transmission/client.py`.
- [ ] Mettre à jour `remove(torrent_id, delete_data=False)`.

## Étape 2 : Page Activité & Routes Téléchargements
- [ ] Écrire des tests dans `tests/test_downloads_web.py` pour :
  - L'accès via `/downloads` et `/activity`.
  - La suppression avec `delete_data`.
  - Le déclenchement du scan Jellyfin via `POST /downloads/scan-jellyfin`.
- [ ] Mettre à jour `torsearch/web/downloads_routes.py` pour supporter `/activity`, `delete_data`, et `scan-jellyfin`.
- [ ] Améliorer les templates `downloads.html` et `partials/downloads_list.html` avec :
  - Débits totaux en en-tête.
  - Barres de progression stylisées avec pourcentages.
  - Statuts lisibles, ETA, nombre de pairs.
  - Boutons de pause, reprise, suppression (avec confirmation).
  - Bouton de scan Jellyfin.
- [ ] Mettre à jour le lien de navigation dans `torsearch/web/templates/base.html` pour afficher `Activite`.

## Étape 3 : Actions Découvrir & Ajout direct en Bibliothèque
- [ ] Écrire des tests dans `tests/test_discover_web.py` pour :
  - L'ajout d'un film en bibliothèque via `POST /discover/library/add`.
  - L'ajout d'une série en bibliothèque via `POST /discover/library/add`.
- [ ] Mettre à jour `torsearch/web/discover_routes.py` pour implémenter la route d'ajout direct.
- [ ] Mettre à jour `torsearch/web/templates/partials/media_results.html` pour que le bouton mette à jour son état en badge « En bibliothèque » avec un swap ciblé.

## Étape 4 : Fiche Détail Modal dans Découvrir
- [ ] Écrire un test dans `tests/test_discover_web.py` pour `GET /discover/{media_type}/{tmdb_id}/modal`.
- [ ] Créer `torsearch/web/templates/partials/media_detail_modal.html`.
- [ ] Ajouter le conteneur modal dans `torsearch/web/templates/base.html` (`#modal-container`).
- [ ] Ajouter la gestion du clic de fermeture dans `torsearch/web/static/app.js`.
- [ ] Ajouter le déclencheur d'ouverture sur les affiches/titres des médias dans `media_results.html`.

## Étape 5 : Validation Qualité & Déploiement
- [ ] Lancer les tests : `pytest -q`.
- [ ] Vérifier l'absence de JS inline : `pytest tests/test_no_inline_js.py -q`.
- [ ] Vérifier le linting : `ruff check torsearch tests`.
- [ ] Vérifier le typage : `mypy`.
- [ ] Mettre à jour `pyproject.toml` (v0.3.4) et `AGENTS.md`.
- [ ] Commiter, taguer (`v0.3.4`), et pusher sur GitHub.
