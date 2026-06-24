# Fiabilité films (re-grab) & plafonnement de l'historique

Date : 2026-06-24

## Contexte

Deux suites directes de la revue projet :

- **A** : la robustesse « re-grab des échecs » ajoutée aux séries n'existe pas côté
  films. `run_movie_cycle` marque un film `grabbed` définitivement → un téléchargement
  mort n'est jamais réessayé et le film reste absent de Jellyfin (trou silencieux).
- **B** : `MonitorHistory` grossit sans limite (chargé + réécrit en entier à chaque
  ajout), et le cooldown séries le scanne désormais à chaque cycle. Croissance infinie =
  démarrage et cycles de plus en plus lents.

## A — Re-grab des films échoués (Jellyfin = vérité)

`WantedMovie` possède déjà `status` et `grabbed_at`. On réutilise le réglage existant
`monitor.regrab_hours` (48 h).

`run_movie_cycle` gagne un paramètre `jellyfin=None`. `owned()` est récupéré **une fois
par cycle**. On itère `library.list()` (tous les films) et on filtre via :

`_movie_needs_grab(movie, jellyfin, owned_map, now, window)` :
- `status == "wanted"` → **oui** (jamais grabbé).
- `status == "grabbed"` :
  - Jellyfin désactivé → **non** (pas de source de vérité, `grabbed` permanent = actuel).
  - Présent dans `owned` (`movie:{tmdb_id}`) → **non** (confirmé).
  - `grabbed_at` dans la fenêtre `now − window` → **non** (téléchargement en cours).
  - Sinon (grabbé mais absent au-delà de la fenêtre) → **oui** (échec, on re-chasse).

Le re-grab passe par le `min_seeders` du profil : un torrent mort à 0 seed est filtré,
donc on ne re-télécharge pas un torrent crevé. `mark_grabbed` réinitialise `grabbed_at`
→ nouvelle fenêtre de 48 h à chaque tentative.

`run_movie_cycle` est câblé dans `_loop` avec `jellyfin=getattr(ctx, "jellyfin", None)`.

## B — Plafonnement de l'historique

`MonitorHistory(path, max_records=1000)`. À l'ajout, on tronque aux **N derniers**
enregistrements (`existing[-max_records:]`). 1000 couvre largement l'UI surveillance et la
fenêtre de cooldown (on ne grab jamais 1000 fois en 48 h). Ordre conservé (récents en
tête via `records()`).

## Dégradation gracieuse
- Films, Jellyfin off → comportement permanent actuel (tests existants intacts).
- `run_movie_cycle(jellyfin=None)` → aucun re-grab (chemin actuel).

## Tests (TDD)
- `test_monitor_runner.py` : film grabbé hors fenêtre + absent de Jellyfin → re-chassé ;
  présent dans Jellyfin → ignoré ; grabbé récemment → ignoré ; Jellyfin off → ignoré.
- `test_monitor_history.py` : au-delà du cap, seuls les N derniers sont conservés, ordre
  récents-d'abord préservé.

## Hors périmètre
- SQLite (point D de la revue) — chantier de fond séparé.
- Plafonnement par âge (on choisit le plafond par nombre, plus simple).
