# Surveillance : fiabilité & efficacité

Date : 2026-06-24

## Contexte

La surveillance séries (`run_series_cycle`) télécharge automatiquement les épisodes
manquants. Trois faiblesses identifiées en revue :

1. **Échec silencieux** : un épisode est marqué `grabbed` au moment du `transmission.add`
   (optimiste). Si le torrent meurt, l'épisode reste « acquis » pour toujours → jamais
   réessayé, jamais dans Jellyfin → trou définitif.
2. **Marteau TMDB/trackers** : `TmdbClient.episodes()` fait 1 + N requêtes (une par
   saison) **par série, par cycle** (toutes les 30 min), même pour des séries terminées.
3. **`jellyfin.owned()` appelé par série** : la liste complète Jellyfin est retéléchargée
   N fois par cycle.

## #1 — Re-grab des échecs (cooldown via historique)

`MonitorHistory` horodate déjà chaque grab (`MonitorRecord.at`, `.search`, `.title`,
`.kind`). On s'en sert comme cooldown, **sans changer le modèle `WantedSeries`**.

Nouveau réglage : `MonitorConfig.regrab_hours: int = 48`.

`_series_have(series, jellyfin, owned_map, records, now, window)` :
- **Jellyfin désactivé** → `have = set(series.grabbed)` (aucune source de vérité, on
  garde le comportement permanent actuel).
- **Jellyfin activé** :
  - `present` = `jellyfin.episodes(itemId)` (∅ si la série n'est pas matchée dans `owned`).
  - À partir des records `grabbed` de cette série (`r.search == series.title`) :
    - `recent` = épisodes grabbés **dans la fenêtre** `now − window` (téléchargement en cours).
    - `historic` = tous les épisodes jamais enregistrés en historique pour la série.
  - `legacy` = `set(series.grabbed) − historic` = épisodes marqués acquis **sans trace**
    d'historique (grabbés avant cette feature) → conservés pour éviter une tempête de
    re-grab au déploiement.
  - `have = present ∪ recent ∪ legacy`.

Effet : un épisode grabbé mais absent de Jellyfin au-delà de `regrab_hours` retombe dans
les manquants → re-chassé. Confirmé dans Jellyfin → reste acquis (via `present`). En vol
(grabbé récemment) → suppression temporaire (via `recent`).

`series_library.mark_grabbed(...)` reste appelé (liste permanente pour le badge « X
épisodes » et le repli Jellyfin-off).

## #2 — Cache TMDB des épisodes diffusés

`TmdbClient` reçoit un cache mémoire TTL pour `episodes(tv_id)` :
- `__init__(..., episode_cache_seconds=6*3600, clock=time.monotonic)` (`clock` injectable
  pour les tests).
- Hit dans le TTL → retour du cache, **zéro requête HTTP**.
- **On ne met pas en cache les résultats vides** (échec réseau ou série sans épisode
  diffusé) → on retente au cycle suivant (détection rapide du 1ᵉʳ épisode).

## #3 — `owned()` une fois par cycle

`run_series_cycle` récupère `owned_map = await jellyfin.owned()` **une seule fois** (si
Jellyfin actif) et le passe à `_series_have`. `history.records()` est aussi lu **une fois
par cycle** et passé en liste.

## Dégradation gracieuse
- Toute erreur Jellyfin/TMDB → set vide → repli (comportement actuel). Aucun crash de cycle.
- Tests existants intacts : le chemin `jellyfin=None / tmdb=None` garde `have =
  series.grabbed` et le mode repli.

## Tests (TDD)
- `test_tmdb.py` : cache hit (2ᵉ appel ne refait pas la requête), expiration TTL (horloge
  injectée), pas de cache sur résultat vide.
- `test_monitor_runner.py` :
  - re-grab : épisode grabbé hors fenêtre + absent de Jellyfin → re-chassé ; grabbé dans
    la fenêtre → ignoré ; `legacy` (grabbed sans historique) → conservé.
  - `owned()` appelé une seule fois quel que soit le nombre de séries.

## Hors périmètre
- Pas d'exposition UI de `regrab_hours` (réglable via `config.yaml`).
- Upgrade qualité, choix du plus petit torrent couvrant, plages `E01-E12` : raffinements
  reportés (n°4/5 de la revue).
