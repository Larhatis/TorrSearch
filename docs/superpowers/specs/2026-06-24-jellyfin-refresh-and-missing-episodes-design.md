# Jellyfin : auto-refresh & détection d'épisodes manquants

Date : 2026-06-24

## Contexte

Aujourd'hui l'API Jellyfin n'est utilisée qu'en lecture (`owned()` → badges « Dans
Jellyfin » + bouton Lire). On exploite deux capacités supplémentaires pour rapprocher
la partie *arr* (Radarr/Sonarr) d'un comportement fiable :

1. **Rafraîchir la bibliothèque Jellyfin** quand un téléchargement se termine.
2. **Cibler les vrais épisodes manquants** d'une série suivie (Sonarr-lite réel).

## Feature 1 — Auto-refresh après complétion

### `JellyfinClient.refresh() -> bool`
- `POST {url}/Library/Refresh?api_key=…`.
- Résilient : aucune exception ne remonte (best-effort), renvoie `True`/`False`.
- No-op (`False`) si Jellyfin n'est pas configuré.

### Détecteur de complétion dans la boucle du moniteur
- Fonction pure `run_jellyfin_refresh(transmission, jellyfin, completed_seen) -> set[int]`.
- À chaque tour : `transmission.list_torrents()` → ensemble des torrents finis
  (`percent >= 100`). Si de nouveaux torrents ont fini depuis le tour précédent
  (`done - completed_seen` non vide) → un seul `jellyfin.refresh()`.
- Renvoie l'ensemble courant des torrents finis (l'état est porté par
  `MonitorRunner._completed_seen`).
- **Indépendant de `monitor.enabled`** : appelé dans `_loop` *après* les cycles gatés,
  donc fonctionne même en usage purement manuel (recherche → download). Il suffit que
  Jellyfin soit configuré. Toute panne Transmission est avalée (la boucle survit).
- Cadence = `monitor.interval_minutes` (le scan n'a pas besoin d'être instantané).

## Feature 2 — Surveillance séries ciblée

### Nouvelles méthodes résilientes (→ `set()` en cas d'échec)
- `TmdbClient.episodes(tv_id) -> set[str]` : `GET /tv/{id}` pour la liste des saisons
  (≥ 1, on saute les spéciaux saison 0), puis `GET /tv/{id}/season/{n}` par saison ;
  on garde les épisodes **diffusés** (`air_date` non vide et `<= aujourd'hui`).
  Clés `S01E01`. = ce qu'on *veut*.
- `JellyfinClient.episodes(item_id) -> set[str]` : `GET /Shows/{item_id}/Episodes` →
  clés `S{ParentIndexNumber:02d}E{IndexNumber:02d}` (on ignore les items sans numéro).
  = ce qu'on *a vraiment*.

### `run_series_cycle` revu
Signature étendue : `(config, series_library, search, transmission, history,
notifier=None, jellyfin=None, tmdb=None)` (paramètres optionnels en fin → tests
existants intacts).

Par série suivie :
- `present` = `jellyfin.episodes(itemId)` si la série est dans `owned()`, sinon ∅.
- `have` = `set(series.grabbed) ∪ present` (le `grabbed` couvre le téléchargé pas encore scanné).
- `aired` = `tmdb.episodes(tmdb_id)` si TMDB actif, sinon ∅.
- **Mode ciblé** (TMDB actif, `aired` non vide) : `missing = aired − have`.
  - Si `missing` vide → série complète & à jour → on saute.
  - On ne grab que les torrents couvrant un épisode encore manquant ; un `remaining`
    mutable évite de grab deux torrents pour le même épisode dans un tour.
  - Pack de saison `S02` : pris s'il couvre au moins un manquant de la saison ; on
    enregistre dans `grabbed` les **clés épisodes réellement couvertes** (`S02E01`…),
    pas la clé saison brute — sinon le dédup du tour suivant casse.
- **Mode repli** (TMDB inactif) : comportement actuel inchangé (grab tout torrent dont
  les épisodes ne sont pas déjà dans `have`).

### Dégradation gracieuse
- TMDB off → repli (comportement actuel).
- Jellyfin off → `have` = `grabbed` seul, `present` = ∅.
- Toute erreur réseau (TMDB/Jellyfin) → set vide → repli. Aucun crash de cycle.

### Câblage
`MonitorRunner._loop` passe `jellyfin=getattr(ctx, "jellyfin", None)` et
`tmdb=getattr(ctx, "tmdb", None)` à `run_series_cycle`, et appelle `run_jellyfin_refresh`.

## Tests (TDD)
- `test_jellyfin.py` : `refresh()` poste sur `/Library/Refresh` (+ no-op désactivé, +
  résilience erreur) ; `episodes()` parse les clés (+ résilience).
- `test_tmdb.py` : `episodes()` agrège les épisodes diffusés, saute spéciaux et non
  diffusés (`air_date` future) (+ résilience).
- `test_monitor_runner.py` : `run_jellyfin_refresh` déclenche un refresh à la nouvelle
  complétion et pas autrement ; `run_series_cycle` ciblé grab uniquement les manquants,
  saute une série complète, gère un pack de saison, et garde le repli quand TMDB est off.

## Hors périmètre
- Pas de hook « download terminé » côté Transmission (on déduit par polling).
- Pas de suppression/cleanup automatique (feature 6 listée séparément).
