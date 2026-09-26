# Conception : Gestion détaillée des séries par saison et épisode (Style Sonarr)

Date : 2026-09-26

## 1. Objectifs

Offrir à l'utilisateur une vue détaillée des saisons et des épisodes pour chaque série suivie ou découverte :
- Afficher l'arborescence complète des saisons et épisodes depuis TMDB.
- Indiquer clairement le statut de chaque épisode :
  - **Disponible** (présent dans Jellyfin)
  - **Telecharge** (dans les téléchargements récupérés / `grabbed`)
  - **A venir** (date de diffusion future)
  - **Manquant** (épisode diffusé mais non possédé)
- Fournir des boutons de recherche 1-clic ciblés :
  - Pour une **saison complète** : `/?q={titre} S{saison:02d}&cat=tv`
  - Pour un **épisode spécifique** : `/?q={titre} S{saison:02d}E{episode:02d}&cat=tv`
- Accès direct depuis la bibliothèque (`/library`) via modal HTMX (`#modal-container`) ou page dédiée (`/series/{tmdb_id}`).

## 2. Architecture et Données

### 2.1 Modèles (`torsearch/models.py`)
- `EpisodeInfo(BaseModel)` :
  - `season_number: int`
  - `episode_number: int`
  - `code: str` (ex: `"S01E01"`)
  - `name: str = ""`
  - `air_date: str | None = None`
  - `overview: str = ""`
- `SeasonInfo(BaseModel)` :
  - `season_number: int`
  - `name: str = ""`
  - `overview: str = ""`
  - `poster_path: str | None = None`
  - `episode_count: int = 0`
  - `episodes: list[EpisodeInfo] = Field(default_factory=list)`
  - Propriétés calculées : `season_tag` (`"S01"`), `poster_url`.

### 2.2 Client TMDB (`torsearch/metadata/tmdb.py`)
- Méthode `seasons(tv_id: int) -> list[SeasonInfo]` :
  - Interroge `/tv/{tv_id}` pour obtenir la liste des saisons (`season_number >= 1`).
  - Interroge en parallèle (`asyncio.gather`) `/tv/{tv_id}/season/{s_num}` pour récupérer le détail des épisodes.
  - Met en cache mémoire avec TTL.
  - Résilient : renvoie une liste vide en cas d'erreur réseau sans lever d'exception.
- Méthode `episodes(tv_id: int) -> set[str]` :
  - Réutilise `seasons(tv_id)` et filtre les épisodes diffusés (`air_date <= today`).

### 2.3 Bibliothèque Séries (`torsearch/library/series.py`)
- Ajout de `get(tmdb_id: int) -> WantedSeries | None` pour retrouver une série par son identifiant TMDB.

### 2.4 Routes Web (`torsearch/web/series_routes.py`)
- Route `GET /series/{tmdb_id}` et `GET /series/{tmdb_id}/detail` :
  - Récupère la série en bibliothèque (si présente).
  - Récupère les métadonnées TMDB (détails + saisons/épisodes).
  - Récupère l'état Jellyfin :
    - Identifiant de la série dans Jellyfin (via `owned` ou recherche).
    - Épisodes présents dans Jellyfin via `jellyfin.episodes(jf_item_id)`.
  - Calcule pour chaque saison et épisode :
    - Statut : `jellyfin` | `grabbed` | `unaired` | `missing`.
    - Nombre d'épisodes acquis vs total.
  - Renvoie le modal `partials/series_detail_modal.html` si requête HTMX (`HX-Request`) ou la page complète `series_detail.html` en navigation directe.

### 2.5 Templates HTML & UI
- `partials/series_detail_modal.html` :
  - Dialogue modal sombre avec backdrop, bouton fermer (`data-modal-close`), compatible avec `app.js`.
  - En-tête : affiche, titre, titre original, badges, synthèse d'avancement globale.
  - Accordéons `<details>` pour chaque saison :
    - Titre de la saison et badge de progression (ex: "8/10 acquis").
    - Bouton « Rechercher la saison complete ».
    - Tableau / grille des épisodes avec code, titre, date, badge statut, et bouton loupe/téléchargement ciblé.
- `partials/series_list.html` :
  - Ajout d'un bouton « Saisons & Episodes » sur chaque carte de série.
  - L'affiche devient également cliquable pour ouvrir les détails.

## 3. Sécurité et Contraintes
- Zéro JS inline : ouverture/fermeture par HTMX et `data-modal-*`.
- Aucun accent dans le balisage HTML (`Saison`, `Episodes`, `Telecharge`, `Manquant`, `Disponible`, etc.).
- Robustesse : aucune panne si TMDB ou Jellyfin est indisponible ou non configuré.
