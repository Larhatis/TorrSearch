# Statuts de connexion dans Réglages

Date : 2026-09-24

## Objectif

Voir d'un coup d'œil, dans Réglages, si Transmission, Jellyfin, TMDB et chaque tracker
répondent — aujourd'hui une erreur ne se remarque qu'indirectement (Découvrir vide,
bandeau dans Téléchargements).

## Conception

### Tests par service (`test() -> (ok, message)`, ne lève jamais)

- `TransmissionClient.test()` : `get_session().version` + `session_stats().torrent_count`
  → `v4.0.6 · 12 torrents` ; toute exception → `(False, redact(message))`.
- `JellyfinClient.test()` : `GET {url}/System/Info?api_key=…` → `omvnas · Jellyfin 10.10.3` ;
  401/403 → « Clé API refusée (401/403). » ; autre code → « Erreur HTTP N. » ; délai →
  « Pas de réponse (timeout). » ; réseau → message masqué ; JSON illisible → « Réponse
  inattendue ».
- `TmdbClient.test()` : `GET /3/configuration?api_key=…` → `OK` ; 401 → « Clé API refusée
  (401). » ; mêmes cas d'erreur que Jellyfin.
- Trackers : `TorznabIndexer.test()` existant (`t=caps`).

Aucun message ne contient de secret (code HTTP seul, ou `torsearch.redact`).

### Orchestration : `torsearch/health.py`

`ServiceStatus(name, state, message)` avec `state` ∈ `ok` | `error` | `off`.
`check_all(ctx, timeout=12.0)` lance tout en parallèle et renvoie, dans l'ordre :
Transmission, Jellyfin, TMDB, chaque tracker (ordre de la config), puis une ligne
Notifications.

- `off` : Jellyfin ou TMDB non configuré (« Non configuré »), tracker désactivé
  (« Désactivé »), Notifications (« N canal(aux) · test manuel dans la section
  Notifications » — pas de test automatique : il enverrait un vrai message ; ligne absente
  s'il n'y a aucun canal).
- `ok` : message « OK » ou « OK · détail » ; TMDB précise « via TMDB_API_KEY » quand la clé
  vient de l'environnement.
- `error` : message du test ; délai global dépassé → « Pas de réponse (délai dépassé). » ;
  exception inattendue → message masqué. Une vérification ne casse jamais le panneau.

### Interface

- Route `GET /settings/status` (routeur Réglages → admin seulement) → partiel
  `partials/status_panel.html` : une ligne par service (pastille verte / rouge / grise,
  nom, message, attribut `data-state`), bouton « Reverifier ».
- `settings.html` : conteneur en tête de page
  `<section id="status-panel" hx-get="/settings/status" hx-trigger="load, settings-saved from:body">`
  (la page s'affiche tout de suite, le panneau se charge ensuite).
- Rafraîchissement après enregistrement : les routes qui modifient Transmission, Jellyfin,
  TMDB ou les trackers renvoient, en cas de succès, l'en-tête `HX-Trigger: settings-saved`.
- Pas de JS inline (règle du chantier 1).

## Tests (TDD)

- `test()` de Transmission (faux client), Jellyfin et TMDB (respx) : succès, clé refusée,
  erreur sans écho de secret.
- `check_all` : ordre et états (ok / error / off), tracker via respx, ligne Notifications,
  délai dépassé, exception masquée, suffixe « via TMDB_API_KEY ».
- Web : `/settings/status` rend les lignes (`check_all` remplacé), Réglages contient le
  conteneur différé, les enregistrements renvoient `HX-Trigger`, invité refusé.

## Hors périmètre

Surveillance continue, pastille dans la navigation, alertes quand un service tombe, test
automatique des notifications, cache des résultats.
