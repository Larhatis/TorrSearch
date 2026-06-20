# Phase A — Découverte TMDB — Design

**Date :** 2026-06-20
**Statut :** validé (carte blanche)

## Objectif

Première brique de l'étoile polaire (tout-en-un remplaçant la stack *arr). Apporter la **couche
métadonnées/découverte** (≈ essence de Jellyseerr) : chercher un film/série par **vrai titre** via
**TMDB**, le voir avec affiche + année + résumé, et **brancher** cette découverte sur le moteur de
recherche torrent existant (« trouver des torrents pour ce titre »).

C'est une tranche verticale minimale qui livre de la valeur tout de suite et sert de fondation aux
phases B (Films/Radarr-lite) et C (Séries/Sonarr-lite).

Non-objectifs (Phase A) : watchlist/suivi/auto-grab (Phase B), épisodes/saisons (Phase C), page
détail riche, multi-utilisateurs/demandes, édition de la clé TMDB dans l'UI Réglages, intégration
Jellyfin.

## Contraintes & décisions (carte blanche)

- Page **/discover séparée** (pas un toggle dans la barre torrent) — la recherche torrent brute
  reste intacte pour l'usage avancé.
- **Langue fr-FR** pour TMDB (titres/résumés en français), codée en dur (pas de config — YAGNI).
- **Pas de page détail** : la carte porte affiche + année + résumé + le bouton bridge.
- Clé TMDB lue depuis `config.yaml`/env (`${TMDB_API_KEY}`), comme les passkeys trackers ;
  **édition dans Réglages différée**.
- Stack inchangée (FastAPI/Jinja/HTMX/Tailwind CDN). Patterns existants réutilisés
  (client httpx injectable + résilient, `AppContext._rebuild`, config frozen + interpolation).
- Au runtime l'utilisateur fournit une **clé API TMDB gratuite** (themoviedb.org). Build/tests
  **hors-ligne** via mocks `respx`.

## Composants & fichiers

### 1. Modèle — `torsearch/models.py` (modifié)

`MediaResult` (pydantic, frozen comme les autres) :
- `tmdb_id: int`, `media_type: str` (`"movie"` | `"tv"`), `title: str`, `year: str | None`,
  `overview: str = ""`, `poster_path: str | None = None`.
- `@computed_field poster_url -> str | None` : `https://image.tmdb.org/t/p/w342{poster_path}`
  si `poster_path`, sinon `None`.

### 2. Config — `torsearch/config.py` (modifié)

`MetadataConfig(BaseModel, frozen)` : `tmdb_api_key: str = ""`. Ajouté à `Config` :
`metadata: MetadataConfig = Field(default_factory=MetadataConfig)`. Interpolation `${VAR}` déjà
gérée par `_interpolate`.

### 3. Client — `torsearch/metadata/tmdb.py` (créé)

`TmdbClient` (même forme que `TorznabIndexer`) :
- `__init__(self, config: MetadataConfig, client: httpx.AsyncClient | None = None, timeout=10.0)`.
- `enabled: bool` → `bool(self._api_key)`.
- `async search(self, query: str) -> list[MediaResult]` :
  - si non `enabled` ou `query` vide → `[]`.
  - GET `https://api.themoviedb.org/3/search/multi` avec
    `params={api_key, query, language: "fr-FR", include_adult: "false"}`.
  - parse `results[]` ; garde `media_type in {"movie","tv"}` (ignore `person`) ; mappe
    `title`/`name`, `release_date`/`first_air_date` → `year` (4 premiers car.), `overview`,
    `poster_path`, `id`.
  - **résilient** : toute exception (réseau, JSON, HTTP≥400) → log warning + `[]`
    (jamais d'exception remontée), comme `TorznabIndexer`.
- Parsing isolé dans une fonction pure `parse_multi(payload: dict) -> list[MediaResult]` (testable
  sans HTTP).

### 4. Contexte — `torsearch/context.py` (modifié)

`AppContext._rebuild` construit `self._tmdb = TmdbClient(self._config.metadata, ...)` ;
exposer `@property tmdb`. Reconstruit au hot-reload (`update_settings`).

### 5. Web — `torsearch/web/discover_routes.py` (créé) + templates

- `GET /discover` → `discover.html` (étend `base.html`). Contexte `{"has_tmdb": ctx.tmdb.enabled}`.
  Si pas de clé → bannière onboarding « Configure ta clé TMDB » (style des autres onboardings).
  Sinon : barre de recherche par titre (`hx-get="/discover/search"`, cible `#media-results`),
  conteneur `#media-results`, et conteneur `#results` (pour les torrents du bridge).
- `GET /discover/search?q=` → `partials/media_results.html` : grille de **cartes affiches**
  (affiche `poster_url` ou placeholder, titre, année, badge type movie/série, résumé tronqué) ;
  chaque carte a un bouton **« Torrents »** :
  `hx-get="/search" hx-vals='{"q": "<title year>", "cat": "<movies|tv>"}' hx-target="#results"`.
  Mapping `media_type` → `cat` : `movie`→`movies`, `tv`→`tv`. Le clic rend `results.html`
  (existant) dans `#results`, réutilisant tout le rendu torrent (badges, santé, Envoyer).
- Routeur inclus dans `create_app`.

### 6. Shell — `torsearch/web/templates/base.html` (modifié)

Ajouter l'entrée nav **Découvrir** (icône `ti-compass`) avec état actif (`path.startswith('/discover')`).

### 7. Doc

`.env.example` + `config.example.yaml` : documenter `TMDB_API_KEY` / section `metadata`.

## Flux de données

1. `/discover` (page) → recherche titre → `hx-get /discover/search` → `ctx.tmdb.search(q)` →
   cartes affiches dans `#media-results`.
2. Carte → bouton « Torrents » → `hx-get /search` (q=titre+année, cat) → `results.html` dans
   `#results` (moteur torrent existant, inchangé).

## Gestion des erreurs / cas limites

- Pas de clé TMDB → page onboarding, pas d'appel réseau.
- Erreur réseau/HTTP/JSON TMDB → `[]` (résilient) → « Aucun média trouvé ».
- `poster_path` absent → placeholder visuel (pas d'image cassée).
- `media_type` person ou autre → ignoré.
- `query` vide → `[]`.

## Tests

- `tests/test_tmdb.py` (respx + fonction pure) :
  - `parse_multi` : mappe movie (`title`/`release_date`) et tv (`name`/`first_air_date`),
    ignore `person`, gère `poster_path` nul, extrait l'année.
  - `enabled` faux sans clé → `search` retourne `[]` sans requête.
  - `search` succès (respx, fixture JSON) → liste de `MediaResult` ; `source`/champs corrects.
  - résilience : HTTP 500 → `[]` ; JSON illisible → `[]`.
- `tests/test_models.py` (ajout) : `MediaResult.poster_url` construit l'URL / `None` si pas
  d'affiche.
- `tests/test_config.py` (ajout) : `metadata.tmdb_api_key` chargé + interpolation `${TMDB_API_KEY}`.
- `tests/test_discover_web.py` (`TestClient` + Fake ctx avec tmdb mocké) :
  - `GET /discover` sans clé → bannière onboarding ; avec clé → barre de recherche.
  - `GET /discover/search?q=...` → cartes (titre, année) + bouton bridge `hx-get="/search"`
    avec le bon `q`/`cat`.
  - nav : `GET /discover` marque « Découvrir » actif (`aria-current`).
- Non-régression : suite existante (167) reste verte.
