# Plan : Bascule torrent bloqué, Fiche film détaillée & Assets locaux

Date : 2026-09-27

## Étape 1 : Bascule automatique en cas de torrent bloqué (Torrent Stalled Fallback)
1. **Modèles & Config** :
   - Ajouter `stalled_hours: int = 2` dans `MonitorConfig`.
   - Ajouter `date_added: datetime | None = None` dans `TorrentInfo` et le renseigner dans `list_torrents()`.
2. **Bibliothèques** :
   - Ajouter `get(self, tmdb_id: int) -> WantedMovie | None` et `unmark_grabbed(self, tmdb_id: int)` dans `MovieLibrary`.
   - Ajouter `unmark_grabbed(self, tmdb_id: int, keys: list[str])` dans `SeriesLibrary`.
   - Tests unitaires dans `tests/test_movie_library.py` et `tests/test_series_library.py`.
3. **Moteur de détection & bascule** :
   - Écrire `handle_stalled_torrents(...)` dans `torsearch/monitor/runner.py`.
   - Intégrer dans `MonitorRunner._loop()`.
   - Écrire les tests unitaires et de cycle dans `tests/test_monitor_stalled_fallback.py`.
4. **Vérification** :
   - `pytest tests/test_movie_library.py tests/test_series_library.py tests/test_monitor_stalled_fallback.py`.

## Étape 2 : Fiche détaillée pour les Films (`/movies/{tmdb_id}`)
1. **Routes Web** :
   - Créer `torsearch/web/movie_routes.py` (ou enrichir `library_routes.py`) avec `GET /movies/{tmdb_id}`, `GET /movies/{tmdb_id}/detail`, `POST /movies/{tmdb_id}/regrab`.
   - Monter les routes dans l'application.
2. **Templates** :
   - Créer `torsearch/web/templates/partials/movie_detail_content.html`.
   - Créer `torsearch/web/templates/partials/movie_detail_modal.html`.
   - Créer `torsearch/web/templates/movie_detail.html`.
   - Mettre à jour `partials/library_list.html` avec poster cliquable et bouton « Details du film ».
   - Mettre à jour `partials/media_detail_modal.html` avec bouton « Details du film » pour les films.
3. **Tests TDD** :
   - Écrire `tests/test_movie_detail_web.py`.
   - Vérifier zéro JS inline : `pytest tests/test_no_inline_js.py`.

## Étape 3 : Autonomie locale des assets (Zéro CDN)
1. **Rapatriement des assets** :
   - Télécharger `htmx.min.js` dans `torsearch/web/static/htmx.min.js`.
   - Télécharger Tabler Icons CSS et police woff2 dans `torsearch/web/static/tabler/`.
   - Télécharger Tailwind CSS standalone ou le bundle autonome dans `torsearch/web/static/tailwind/`.
2. **Mise à jour du layout** :
   - Remplacer les URLs CDN de `base.html` par les chemins locaux `/static/...`.
3. **Vérification** :
   - Vérifier que l'application charge correctement sans connexion CDN.
   - Vérifier `pytest tests/test_no_inline_js.py`.

## Étape 4 : Validation finale & Publication
- Lancer la suite complète : `ruff check torsearch tests`, `mypy`, `pytest -q`.
- Bump version `0.3.7` dans `pyproject.toml` et mise à jour de `AGENTS.md`.
- Commit, tag `v0.3.7`, push `main` et tag `v0.3.7`.
