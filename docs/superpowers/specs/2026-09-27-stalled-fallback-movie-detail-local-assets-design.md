# Conception : Bascule torrent bloqué, Fiche film détaillée & Assets locaux

Date : 2026-09-27

## 1. Objectifs

Ce lot apporte trois avancées majeures :
1. **Détection d'échec & Bascule automatique sur une autre release (Torrent Stalled Fallback)** :
   - Détecter dans Transmission les torrents bloqués (0 % avec 0 pairs actifs après un délai paramétrable, ou statut en erreur fatale).
   - Supprimer le torrent bloqué de Transmission avec ses données.
   - Ajouter l'infohash et le titre à la `Blacklist` SQLite pour ne plus jamais reprendre cette release.
   - Démarquer le statut `grabbed` du film ou des épisodes de la série.
   - Permettre au moteur de surveillance d'auto-grabber immédiatement la prochaine release candidate.
2. **Fiche détaillée pour les Films (`/movies/{tmdb_id}`)** :
   - Aligner l'expérience des films sur celle des séries (v0.3.6).
   - Vue modale HTMX (`#modal-container`) depuis la Bibliothèque et Découvrir, ou page dédiée `/movies/{tmdb_id}`.
   - Synopsis complet, date, note, statut Jellyfin unifié (avec bouton de lecture direct).
   - Informations sur la release déjà obtenue (`grabbed_title`, date).
   - Boutons de recherche 1-clic pré-filtrés par qualité (Tous les torrents, 1080p, 4K / 2160p, REMUX).
   - Bouton « Regrab » pour relancer la recherche et améliorer la qualité d'un film.
3. **Autonomie locale des assets (Zéro CDN)** :
   - Embarquer HTMX, Tabler Icons (CSS + fonte web woff2) et les styles nécessaires directement dans `torsearch/web/static/`.
   - Éliminer les dépendances externes vers les CDN (cdnjs, unpkg, jsdelivr, google fonts).
   - Chargement instantané hors-ligne ou sur réseau local isolé sans accès Internet.

## 2. Architecture & Conception technique

### 2.1 Bascule torrent bloqué (`torsearch/monitor/runner.py`)
- Modèle de configuration :
  - Ajouter `stalled_hours: int = 2` dans `MonitorConfig` (`torsearch/config.py`).
- Bibliothèque :
  - Ajouter `unmark_grabbed(tmdb_id: int)` dans `MovieLibrary`.
  - Ajouter `unmark_grabbed(tmdb_id: int, keys: list[str])` dans `SeriesLibrary`.
- Détection dans `torsearch/monitor/runner.py` :
  - `async def handle_stalled_torrents(transmission, library, series_library, history, blacklist, notifier=None, config=None) -> list[str]` :
    - Récupère `transmission.list_torrents()`.
    - Pour chaque torrent :
      - En erreur (`t.error_string` et `t.percent < 100.0`) OU
      - Bloqué (`t.percent == 0.0`, `t.down_rate == 0`, `t.peers_sending == 0`, `t.status != "stopped"`, et temps écoulé depuis l'ajout >= `stalled_hours`).
    - Actions :
      1. `blacklist.add(t.info_hash, t.name, reason="stalled")`
      2. `await transmission.remove(t.id, delete_data=True)`
      3. Trouver et démarquer le film correspondant dans `MovieLibrary` si applicable.
      4. Trouver et démarquer les épisodes correspondants dans `SeriesLibrary` via `parse_episodes(t.name)`.
      5. Notification éventuelle.
  - Intégré au début de chaque cycle dans `MonitorRunner._loop()`.

### 2.2 Fiche détaillée Films (`torsearch/web/movie_routes.py` ou `library_routes.py`)
- Méthode `get(tmdb_id: int) -> WantedMovie | None` dans `MovieLibrary`.
- Routes :
  - `GET /movies/{tmdb_id}` (page complète `movie_detail.html`).
  - `GET /movies/{tmdb_id}/detail` (modale partial `partials/movie_detail_modal.html`).
  - `POST /movies/{tmdb_id}/regrab` (démarque le film et redirige vers la recherche ou relance l'auto-grab).
- Templates :
  - `partials/movie_detail_content.html`
  - `partials/movie_detail_modal.html`
  - `movie_detail.html`
  - Mise à jour de `partials/library_list.html` avec affiche cliquable et bouton « Details du film ».
  - Mise à jour de `partials/media_detail_modal.html` avec bouton détails film.

### 2.3 Assets locaux (`torsearch/web/static/`)
- Fichiers locaux :
  - `torsearch/web/static/htmx.min.js`
  - `torsearch/web/static/tabler-icons.min.css`
  - `torsearch/web/static/fonts/tabler-icons.woff2`
  - `torsearch/web/static/tailwind.min.css` (ou bundle standalone Tailwind)
- Mise à jour de `base.html` :
  - Remplacer les `<link>` et `<script>` CDN par les chemins `/static/...`.

## 3. Sécurité et Contraintes
- Zero inline JS (`test_no_inline_js.py`).
- Pas d'accents dans les templates HTML.
- TDD : tests unitaires et d'intégration avant toute modification.
