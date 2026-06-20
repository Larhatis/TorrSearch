# Phase B — Bibliothèque Films (Radarr-lite) — Design

**Date :** 2026-06-20
**Statut :** validé

## Objectif

Deuxième brique de l'étoile polaire (remplacer Radarr). Une **bibliothèque de films « voulus »**
ajoutés depuis la découverte TMDB (Phase A) : le moteur de **surveillance** existant cherche en
boucle un torrent conforme à un **profil de qualité global** et, dès qu'il en trouve un,
l'**envoie à Transmission** et passe le film en **« obtenu »**.

Réutilise au maximum l'acquis : `select_new`/`apply`/`grab_key` (picking), `MonitorHistory`
(patron du store + journal), `Notifier` (notifications), le toggle/interval `monitor` global.

Non-objectifs (Phase B) : séries (Phase C), profil de qualité par film, gestion/renommage de
fichiers, multi-versions, import d'une bibliothèque existante, intégration Jellyfin.

## Décisions (validées)

- **Profil de qualité global** (pas par film) : `qualities` + `min_seeders`, dans les réglages,
  éditable via une petite section Réglages.
- Persistance des films dans un **store séparé `data/library.json`** (pas dans settings.json) :
  le monitor le met à jour en tâche de fond (statut voulu → obtenu), distinct des réglages
  utilisateur.
- Films en **auto-grab**, gardés par le **toggle surveillance global existant** (OFF par défaut,
  opt-in). La page Bibliothèque indique si la surveillance est désactivée.
- **Dédup par statut** : une fois « obtenu », le film n'est plus recherché.

## Composants & fichiers

### 1. Modèle — `torsearch/models.py` (modifié)

`WantedMovie(BaseModel)` :
- `tmdb_id: int`, `title: str`, `year: str | None = None`, `poster_path: str | None = None`,
  `status: str = "wanted"` (`"wanted"` | `"grabbed"`),
  `added_at: datetime`, `grabbed_at: datetime | None = None`, `grabbed_title: str | None = None`.
- `@computed_field poster_url` → même logique que `MediaResult` (w342) ou `None`.

### 2. Config — `torsearch/config.py` (modifié)

`LibraryConfig(BaseModel, frozen)` :
- `qualities: list[str] = ["2160p", "1080p"]`, `min_seeders: int = 1`.

Ajouté à `Config` : `library: LibraryConfig = Field(default_factory=LibraryConfig)`.
Mutation settings : un helper dans `torsearch/settings/mutations.py` pour remplacer `library`
(comme les mutations existantes), appelé par `POST /settings/library`.

### 3. Store — `torsearch/library/__init__.py` (vide) + `torsearch/library/movies.py` (créé)

`MovieLibrary` (calqué sur `MonitorHistory`, JSON atomique) :
- `list() -> list[WantedMovie]` (ordre d'ajout).
- `wanted() -> list[WantedMovie]` (statut `wanted`).
- `add(movie: WantedMovie) -> bool` : ignore si `tmdb_id` déjà présent (dédup) ; renvoie ajouté ?.
- `remove(tmdb_id: int) -> None`.
- `mark_grabbed(tmdb_id: int, grabbed_title: str, at: datetime) -> None` : statut → `grabbed`.

### 4. Cycle monitor — `torsearch/monitor/runner.py` (modifié)

`run_movie_cycle(config, library, search_service, transmission, history, notifier=None) -> list[MonitorRecord]` :
- si `not config.monitor.enabled` → `[]`.
- pour chaque `movie` dans `library.wanted()` :
  - `query = f"{movie.title} {movie.year}".strip()` ; `results = await search_service.search(query, Category.MOVIES)`.
  - `filters = ResultFilters(min_seeders=config.library.min_seeders, qualities=config.library.qualities, sort="seeders", direction="desc")`.
  - `pick = select_new(results, filters, seen=set())` (le statut gère la dédup ; `select_new`
    réutilisé tel quel).
  - si `pick` : `transmission.add(pick.download_url)` ; `library.mark_grabbed(movie.tmdb_id, pick.title, now)` ;
    `record = MonitorRecord(search=f"{movie.title} ({movie.year})", title=pick.title, source=pick.source, infohash=pick.infohash, download_url=pick.download_url, kind="grabbed", at=now)` ;
    `history.add(record)` ; notif (tolérante).
  - résilience : toute exception sur un film → log + `continue` (un film ne casse pas le cycle).

`MonitorRunner.__init__` reçoit `library` ; `_loop` appelle `run_cycle(...)` **puis**
`run_movie_cycle(...)` à chaque tour.

### 5. Câblage — `torsearch/main.py` + `torsearch/web/routes.py` (modifiés)

`build_app` crée `library = MovieLibrary(library_path)` (`data/library.json`, env
`TORSEARCH_LIBRARY`), le passe à `create_app(..., library=library)` (→ `app.state.library`) et à
`MonitorRunner(ctx, history, library=library)`. Mirroir exact de `history`.

### 6. Web — `torsearch/web/library_routes.py` (créé) + templates

- `POST /library/add` (form `tmdb_id`, `title`, `year`, `poster_path`) → `library.add(WantedMovie(...))`
  → renvoie `partials/toast.html` (« Ajouté à la bibliothèque » / « Déjà présent »).
- `GET /library` → `library.html` : grille d'affiches des films, **badge de statut**
  (Voulu / Obtenu), bouton **Retirer** (`POST /library/{tmdb_id}/remove` → re-rend la liste) ;
  bandeau d'info si `monitor.enabled` est faux (« Active la surveillance pour l'auto-grab »).
- Bouton **« Ajouter »** ajouté sur les cartes de `partials/media_results.html`
  (`hx-post="/library/add"` avec `hx-vals` en **guillemets simples** + `tojson`, cf. correctif
  Phase A) — uniquement pour `media_type == "movie"` (les séries = Phase C).
- Nav : entrée **Bibliothèque** (`ti-bookmark`) + état actif (`path.startswith('/library')`).
- Routeur inclus dans `create_app`.

### 7. Réglages — section profil

Petit formulaire dans `settings.html` (qualités en cases + seeders min) → `POST /settings/library`
→ mutation `library` → `ctx.update_settings`. Toast de confirmation.

## Flux de données

1. Découvrir → « Ajouter » (carte film) → `POST /library/add` → `data/library.json` (statut `wanted`).
2. `MonitorRunner._loop` (si `monitor.enabled`) → `run_movie_cycle` → pour chaque film voulu,
   recherche + filtres profil → `select_new` → grab Transmission → `mark_grabbed` → historique + notif.
3. `GET /library` reflète l'état (voulu/obtenu) lu depuis le store.

## Gestion des erreurs / cas limites

- Surveillance OFF → aucun cycle film (bandeau d'info sur `/library`).
- Aucun release conforme pour un film → reste « voulu », réessayé au prochain tour.
- Ajout d'un film déjà présent → ignoré (dédup `tmdb_id`), toast « déjà présent ».
- Erreur réseau/tracker/Transmission sur un film → loggée, le cycle continue.
- `data/library.json` absent → bibliothèque vide.

## Tests

- `tests/test_models.py` : `WantedMovie.poster_url`.
- `tests/test_config.py` : défauts `LibraryConfig` + chargement.
- `tests/test_movie_library.py` : `add`/dédup, `remove`, `wanted`, `mark_grabbed` (persistance JSON).
- `tests/test_monitor_runner.py` (ajouts) : `run_movie_cycle` grab+mark_grabbed+history quand
  release conforme ; ne grabbe pas si `monitor` off ; respecte le profil (qualité/seeders) ;
  un film en erreur n'interrompt pas le cycle ; film déjà « grabbed » ignoré.
- `tests/test_library_web.py` : `GET /library` liste + badges + bandeau si monitor off ;
  `POST /library/add` ajoute ; `POST /library/{id}/remove` retire ; bouton « Ajouter » présent
  sur les cartes film de la découverte ; nav « Bibliothèque » active.
- `tests/test_settings_web.py` (ajout) : `POST /settings/library` met à jour le profil.
- Non-régression : suite existante (185) reste verte.
